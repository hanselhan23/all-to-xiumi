"""Click the real copy button, paste natively, and compare text/media/styles.

This checks a browser clipboard round trip. WeChat save/reopen is a separate test.
"""
import argparse
import base64
import ctypes
import hashlib
import io
import json
import os
import re
from pathlib import Path

from PIL import Image, ImageChops
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait


SNAPSHOT = """
const root=document.querySelector(arguments[0]);
const props=['font-size','font-family','font-weight','font-style','line-height','letter-spacing','color','background-color','background-image','padding-top','padding-right','padding-bottom','padding-left','margin-top','margin-right','margin-bottom','margin-left','border-top-width','border-top-color','border-top-style','border-radius','box-shadow','display','text-align','opacity'];
const styled=[...(root.hasAttribute('style')?[root]:[]),...root.querySelectorAll('[style]')];
return {text:root.innerText.replace(/\\r\\n/g,'\\n').trim(),images:[...root.querySelectorAll('img')].map(e=>({src:e.src,w:e.naturalWidth,h:e.naturalHeight})),styles:styled.map(e=>({tag:e.tagName,values:Object.fromEntries(props.map(p=>[p,getComputedStyle(e).getPropertyValue(p)]))}))};
"""


def normalized(snapshot):
    # Browsers add structural paragraph newlines; keep each text-bearing leaf intact.
    snapshot['text'] = re.sub(r'\s*\n\s*', '\n', snapshot['text'])
    for image in snapshot['images']:
        raw = base64.b64decode(image.pop('src').split(',', 1)[1])
        image['sha256'] = hashlib.sha256(raw).hexdigest()
    return snapshot


def capture(driver, selector):
    bounds=driver.execute_script("const r=document.querySelector(arguments[0]).getBoundingClientRect();return {x:r.x+scrollX,y:r.y+scrollY,width:r.width,height:r.height,scale:1}",selector)
    result=driver.execute_cdp_cmd('Page.captureScreenshot',{'format':'png','clip':bounds,'captureBeyondViewport':True})
    return Image.open(io.BytesIO(base64.b64decode(result['data']))).convert('RGB')


def windows_clipboard_metrics():
    if os.name!='nt':return {'format_check':'not_available'}
    user=ctypes.windll.user32;kernel=ctypes.windll.kernel32
    user.GetClipboardData.restype=ctypes.c_void_p;kernel.GlobalLock.argtypes=[ctypes.c_void_p];kernel.GlobalLock.restype=ctypes.c_void_p
    kernel.GlobalSize.argtypes=[ctypes.c_void_p];kernel.GlobalSize.restype=ctypes.c_size_t;kernel.GlobalUnlock.argtypes=[ctypes.c_void_p]
    fmt=user.RegisterClipboardFormatW('HTML Format')
    if not user.OpenClipboard(None):raise RuntimeError('Cannot open Windows clipboard')
    try:
        handle=user.GetClipboardData(fmt)
        if not handle:raise RuntimeError('Clipboard has no HTML Format')
        pointer=kernel.GlobalLock(handle)
        try:raw=ctypes.string_at(pointer,kernel.GlobalSize(handle))
        finally:kernel.GlobalUnlock(handle)
        text=raw.decode('utf-8',errors='replace')
        return {'format':'Windows CF_HTML','bytes':len(raw),'embedded_image_occurrences':text.count('data:image/'),'has_plain_text':bool(user.IsClipboardFormatAvailable(13))}
    finally:user.CloseClipboard()


def verify(sample, *, reference=None, report=None, visual=None, driver_path=None):
    options=webdriver.ChromeOptions()
    options.add_argument('--disable-search-engine-choice-screen')
    driver=webdriver.Chrome(service=webdriver.ChromeService(executable_path=driver_path) if driver_path else None,options=options)
    wait=WebDriverWait(driver,30)
    result={'sample':str(sample),'reference':str(reference) if reference else None,'widths':[],
            'wechat_save_validation':'not_tested','scope':'Browser native copy/paste; not WeChat backend sanitization'}
    excerpts=[]
    try:
        for width in (375,768):
            driver.execute_cdp_cmd('Emulation.setDeviceMetricsOverride',{'width':width,'height':900,'deviceScaleFactor':1,'mobile':False})
            baseline=None;baseline_pixels=None
            if reference:
                driver.get(reference.as_uri())
                wait.until(lambda d:d.execute_script("return [...document.querySelectorAll('#gzh-content img')].every(e=>e.complete&&e.naturalWidth)"))
                baseline=normalized(driver.execute_script(SNAPSHOT,'#gzh-content'))
                baseline_pixels=capture(driver,'#gzh-content')
            driver.get(sample.as_uri())
            wait.until(lambda d:d.execute_script("return [...document.querySelectorAll('#gzh-content img')].every(e=>e.complete&&e.naturalWidth)"))
            expected=normalized(driver.execute_script(SNAPSHOT,'#gzh-content'))
            original_pixels=capture(driver,'#gzh-content')
            driver.find_element(By.ID,'gzhCopyBtn').click()
            wait.until(lambda d:'已复制' in d.find_element(By.ID,'gzhToast').text)
            clipboard=windows_clipboard_metrics()
            # A bare independent editor: no source article stylesheet or paste hook.
            driver.get('data:text/html;charset=utf-8,<meta charset="utf-8"><style>body{margin:0;background:%23eef0f2}.stage{max-width:700px;margin:78px auto 64px;padding:0 8px}</style><div class="stage"><div id="paste-target" contenteditable="true"></div></div>')
            target=driver.find_element(By.ID,'paste-target')
            driver.execute_script("arguments[0].style.minHeight='40px'",target)
            target.click();target.send_keys(Keys.CONTROL,'v')
            wait.until(lambda d:len(d.find_elements(By.CSS_SELECTOR,'#paste-target img'))==len(expected['images']))
            wait.until(lambda d:d.execute_script("return [...document.querySelectorAll('#paste-target img')].every(e=>e.complete&&e.naturalWidth)"))
            actual=normalized(driver.execute_script(SNAPSHOT,'#paste-target'))
            # Exclude the neutral editor's own min-height from the style snapshot.
            actual['styles']=actual['styles'][1:]
            driver.execute_script("document.activeElement.blur();window.getSelection().removeAllRanges()")
            pasted_pixels=capture(driver,'#paste-target')
            checks={'width':width,'images':len(actual['images']),'media_bytes_match':actual['images']==expected['images'],
                    'text_match':actual['text']==expected['text'],'computed_styles_match':actual['styles']==expected['styles'],
                    'reference_media_match':baseline is None or baseline['images']==expected['images'],
                    'reference_styles_match':baseline is None or baseline['styles']==expected['styles'],
                    'reference_text_match':baseline is None or baseline['text']==expected['text'],'clipboard':clipboard}
            for label,left,right in [('source_to_sample',baseline_pixels,original_pixels),('sample_to_paste',original_pixels,pasted_pixels)]:
                if left is not None:
                    checks[label+'_same_size']=left.size==right.size
                    checks[label+'_pixel_equal']=left.size==right.size and ImageChops.difference(left,right).getbbox() is None
            result['widths'].append(checks)
            if not all(checks[key] for key in ('media_bytes_match','text_match','computed_styles_match','reference_media_match','reference_styles_match','reference_text_match')):
                # Diagnostics remain in the report; media data are never dumped.
                result['style_differences']=[{'index':i,'expected':a,'actual':b} for i,(a,b) in enumerate(zip(expected['styles'],actual['styles'])) if a!=b][:10]
                result['expected_style_count']=len(expected['styles']);result['actual_style_count']=len(actual['styles'])
                raise AssertionError('Clipboard round trip changed text, media, or styles')
            if width==375:
                for y in (0,max(0,original_pixels.height//2-300),max(0,original_pixels.height-600)):
                    strips=[pic.crop((0,y,min(700,pic.width),min(pic.height,y+600))) for pic in (baseline_pixels or original_pixels,original_pixels,pasted_pixels)]
                    canvas=Image.new('RGB',(sum(pic.width for pic in strips),600),'white');x=0
                    for pic in strips:canvas.paste(pic,(x,0));x+=pic.width
                    excerpts.append(canvas)
        result['clipboard_validation']='passed'
    finally:
        driver.quit()
        if report:
            report.parent.mkdir(parents=True,exist_ok=True);report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        if visual and excerpts:
            canvas=Image.new('RGB',(max(pic.width for pic in excerpts),sum(pic.height for pic in excerpts)),'white');y=0
            for pic in excerpts:canvas.paste(pic,(0,y));y+=pic.height
            canvas.save(visual)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sample',type=Path);parser.add_argument('--reference',type=Path)
    parser.add_argument('--report',type=Path);parser.add_argument('--visual',type=Path);parser.add_argument('--driver-path')
    args=parser.parse_args()
    result=verify(args.sample.resolve(),reference=args.reference.resolve() if args.reference else None,report=args.report,visual=args.visual,driver_path=args.driver_path)
    print(json.dumps(result,ensure_ascii=False,indent=2))
