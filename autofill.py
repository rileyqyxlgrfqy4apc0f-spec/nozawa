# -*- coding: utf-8 -*-
"""
山のホテル大瀧 訂房自動填入 — 一次開多個視窗版 (Selenium)
--------------------------------------------------
它會做什麼：
  * 你選幾筆，它就開幾個「各自獨立」的 Chrome 視窗
  * 每個視窗自動切月份、點日期、設好泊數 / 房數 / 男女人數
  * 全部開著讓你一個一個核對、結帳

它「不會」做什麼：
  * 不會自動按「確認 / 送出」、不會自動填卡、不會自動付款
    結帳請你自己在各視窗手動完成（而且建議一筆一筆做）。

為什麼用「獨立設定檔」：
  每個視窗各自一條連線，互不干擾。你在其中一個結帳，
  其他 7 個已填好的內容不會被蓋掉。

--------------------------------------------------
安裝（VS Code 終端機貼一次）：
    pip install selenium
  電腦需先裝好 Google Chrome。Selenium 4.6+ 會自動處理 driver。

執行：
  改下面的 WHICH_LIST 選要開哪幾筆，存檔後按 ▶ 執行，
  或終端機： python otaki_autofill_multi.py

⚠️ 提醒：一次開 8 個 Chrome 蠻吃記憶體/CPU，機器慢的話建議分兩批
  （例如先 [0,1,2,3]，結帳完再 [4,5,6,7]）。
"""

import time
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

BASE = "https://reserve.489ban.net/client/hotelohtaki/0/detail/"

# ============================================================
#  預約清單（idx 0~7）
# ============================================================
BOOKINGS = [
    {"plan": "933391", "name": "7晚 1男1女",        "year": 2027, "month": 1, "day": 16, "nights": 7, "rooms": 1, "people": {"男性": 1, "女性": 1}},  # 0
    {"plan": "933391", "name": "6晚 1男1女",        "year": 2027, "month": 1, "day": 16, "nights": 6, "rooms": 1, "people": {"男性": 1, "女性": 1}},  # 1
    {"plan": "933392", "name": "7晚 3女",           "year": 2027, "month": 1, "day": 16, "nights": 7, "rooms": 1, "people": {"女性": 3}},              # 2
    {"plan": "933389", "name": "7晚 2男",           "year": 2027, "month": 1, "day": 16, "nights": 7, "rooms": 1, "people": {"男性": 2}},              # 3
    {"plan": "933393", "name": "7晚 2男",           "year": 2027, "month": 1, "day": 16, "nights": 7, "rooms": 1, "people": {"男性": 2}},              # 4
    {"plan": "933389", "name": "5晚 1男1女",        "year": 2027, "month": 1, "day": 16, "nights": 5, "rooms": 1, "people": {"男性": 1, "女性": 1}},  # 5
    {"plan": "933389", "name": "5晚 1男",           "year": 2027, "month": 1, "day": 16, "nights": 5, "rooms": 1, "people": {"男性": 1}},              # 6
    {"plan": "933392", "name": "6晚 2女 (1/17入住)", "year": 2027, "month": 1, "day": 17, "nights": 6, "rooms": 1, "people": {"女性": 2}},             # 7
]

# ============================================================
#  要開哪幾筆？(填 idx)  例：全部 = [0,1,2,3,4,5,6,7]
# ============================================================
#WHICH_LIST = [0, 1, 2, 3, 4, 5, 6, 7]
WHICH_LIST = [0, 1]
# ============================================================
#  測試模式：執行「python autofill.py -test」時，
#  改用這筆「現在就能訂」的 9/8 方案，開 8 個視窗跑完整流程（含填表）。
#  用來在 1 月方案還沒開放前，先演練 8 視窗的實際情況。
# ============================================================
TEST_BOOKING = {"plan": "917009", "name": "測試 9/8 7晚 1男1女", "year": 2026,
                "month": 9, "day": 8, "nights": 7, "rooms": 1,
                "people": {"男性": 1, "女性": 1}}
TEST_COUNT = 8   # 測試模式要開幾個視窗

OPEN_GAP = 1.5   # 每個視窗之間間隔幾秒開（避免同時猛戳伺服器）
LOAD_WAIT = 12   # 等頁面畫好的「上限」秒數；畫好就會提早繼續，不會真的等滿

# ============================================================
#  是否自動進到「個人情報入力」頁並填好訂房者資料
#    True  = 填完第一頁後，自動點「お見積りの確認/個人情報入力」→ 填訂房者資料 → 停在確認前（不會送出）
#    False = 只填第一頁（日期/泊數/人數），停在原本那頁
#  ⚠️ 1 月方案 2026/08/01 10:00 才開放；開放前按不了下一步，程式會自動停在第一頁。
# ============================================================
FILL_CONTACT = True

# 訂房者資料（8 筆共用；若某筆要不同，可自行改這裡再單獨跑那筆）
GUEST = {
    "last": "蔡", "first": "宜真",          # 氏名（姓/名）
    "lastk": "さい", "firstk": "ぎしん",     # ふりがな（姓/名）
    "email": "wentrip2023@gmail.com",
    "bday": "1990/12/12",                   # 生年月日
    "pref": "東京都",                        # 都道府県
    "zip": "1100016",                       # 郵便番号（無橫線）
    "addr": "台東区台東3丁目41-7",            # 市区町村郡/番地
    "tel": "886932791240",                  # 連絡先（主）
    "traffic": "1",                         # 当日交通手段：1=車 2=JR・電車 3=その他
    "checkin_h": "21", "checkin_m": "00",   # チェックイン予定時間
    "payment": "on_site",                   # 付款：on_site=現地決済 / credit=信用卡事前決済
    "note": ("13:00頃に成田空港へ到着予定です。そこからタクシーでホテルへ向かい、"
             "19:00頃到着予定です。到着が遅れる場合は、運転手より電話にてご連絡いたします。"),
}


JS_FILL = r"""
var cfg = arguments[0];
var log=function(){var a=[].slice.call(arguments);a.unshift('%c[大瀧]','color:#d6a23e;font-weight:bold');console.log.apply(console,a);};
var norm=function(s){return (s||'').replace(/\s/g,'');};
var wait=function(ms){return new Promise(function(r){setTimeout(r,ms);});};
// 一邊等一邊偵測：fn() 一有結果就馬上繼續，最多等 max 毫秒
var waitFor=function(fn,max,step){step=step||50;return new Promise(function(res){var s=Date.now();(function t(){var v;try{v=fn();}catch(e){v=null;}if(v){res(v);return;}if(Date.now()-s>max){res(null);return;}setTimeout(t,step);})();});};
function setSelect(sel,val){
  if(!sel) return false;
  var v=String(val), opts=[].slice.call(sel.options), opt=null, i;
  for(i=0;i<opts.length;i++){ if(opts[i].value===v){opt=opts[i];break;} }
  if(!opt){ for(i=0;i<opts.length;i++){ var t=norm(opts[i].textContent); if(t===v||t===v+'泊'||t===v+'名'||t===v+'室'){opt=opts[i];break;} } }
  if(!opt) return false;
  sel.value=opt.value;
  sel.dispatchEvent(new Event('input',{bubbles:true}));
  sel.dispatchEvent(new Event('change',{bubbles:true}));
  return true;
}
(async function(){
  var monthLabel=cfg.year+'年'+cfg.month+'月', shortLabel=cfg.month+'月';
  function findTab(){
    var tabs=[].slice.call(document.querySelectorAll('a,li,button,span,div'));
    for(var i=0;i<tabs.length;i++){
      var t=norm(tabs[i].textContent||'');
      if((t===norm(monthLabel)||t===norm(shortLabel)) && tabs[i].offsetParent!==null) return tabs[i];
    }
    return null;
  }
  function findCell(){
    var tables=document.querySelectorAll('table'), ti, tds, di;
    for(ti=0; ti<tables.length; ti++){
      tds=tables[ti].querySelectorAll('td');
      for(di=0; di<tds.length; di++){
        var m=(tds[di].textContent||'').trim().match(/^(\d{1,2})(?!\d)/);
        if(m && parseInt(m[1],10)===cfg.day && (/円/.test(tds[di].textContent) || tds[di].querySelector('a,button,[onclick]'))) return tds[di];
      }
    }
    return null;
  }
  // 等月份頁籤 render 出來再點（原本頁面沒好就撲空）
  var tab=await waitFor(findTab, 8000);
  if(tab){ tab.click(); log('切到月份 '+monthLabel); }
  else log('未找到月份頁籤，假設已在 '+monthLabel);
  // 等「可點的目標日期格」出現再點（切月份是非同步的，等月曆 render 好）
  var cell=await waitFor(findCell, 8000);
  if(!cell){ log('DATE_NOT_FOUND'); window.__otaki_ok=false; return; }
  var target=cell.querySelector('a,button,[onclick]')||cell;
  target.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true,view:window}));
  log('已點選 '+cfg.day+' 號');
  // 用結構特徵找泊数/部屋数（不靠「泊数」文字，因為那兩字跟選單不同格）：
  //   部屋数＝非人數欄、選項1開頭約10個；泊数＝非人數欄裡剩下選項最多的那個
  function findSelects(){
    var pool=[].slice.call(document.querySelectorAll('select')).filter(function(s){return !s.closest('tr');});
    var rooms=null, i;
    for(i=0;i<pool.length;i++){ if(pool[i].options.length>=1 && pool[i].options.length<=12 && pool[i].options[0].value==='1'){ rooms=pool[i]; break; } }
    var nights=null, maxN=-1;
    for(i=0;i<pool.length;i++){ if(pool[i]===rooms) continue; if(pool[i].options.length>maxN){ maxN=pool[i].options.length; nights=pool[i]; } }
    return {nights:nights, rooms:rooms};
  }
  function hasNight(sel){ if(!sel) return false; var os=sel.options,k; for(k=0;k<os.length;k++){ if(String(os[k].value)===String(cfg.nights)||norm(os[k].textContent)===String(cfg.nights)||norm(os[k].textContent)===String(cfg.nights)+'泊') return true; } return false; }
  // 等泊数下拉出現且已含目標晚數選項就繼續（頁面一 render 好即走）
  var found=await waitFor(function(){
    var f=findSelects();
    return (f.nights && hasNight(f.nights)) ? f : null;
  },8000);
  found=found||findSelects();
  var nightsSel=found.nights, roomsSel=found.rooms;
  log(setSelect(nightsSel,cfg.nights)?('泊数 = '+cfg.nights):'⚠️ 泊数設定失敗');
  // 驗證真的設進去了；沒設到就再試一次
  if(nightsSel && String(nightsSel.value)!==String(cfg.nights)){
    setSelect(nightsSel,cfg.nights);
    log('泊数 重試 → 現在＝'+nightsSel.value);
  }
  log(setSelect(roomsSel,cfg.rooms)?('部屋数 = '+cfg.rooms):'⚠️ 部屋数設定失敗');
  await wait(200);
  var rows=[].slice.call(document.querySelectorAll('tr'));
  Object.keys(cfg.people||{}).forEach(function(label){
    var count=cfg.people[label], row=null, r, cells, c;
    for(r=0;r<rows.length;r++){
      cells=rows[r].querySelectorAll('td,th');
      for(c=0;c<cells.length;c++){ if(norm(cells[c].textContent)===norm(label)){ row=rows[r]; break; } }
      if(row) break;
    }
    var sel=row?row.querySelector('select'):null;
    log(setSelect(sel,count)?(label+' = '+count):('⚠️ 人數設定失敗：'+label));
  });
  window.__otaki_ok=true;
  log('✅ 完成，請人工核對後自行結帳。');
})();
"""


def _poll(driver, js, max_wait, step=0.2):
    """每 step 秒問一次 js；一有結果(非 None/非 False)就回傳，最多等 max_wait 秒。"""
    end = time.time() + max_wait
    while time.time() < end:
        try:
            v = driver.execute_script(js)
            if v:
                return v
        except Exception:
            pass
        time.sleep(step)
    return None


# 點「お見積りの確認/個人情報入力」按鈕（找真正的按鈕，不要點到外層容器）
JS_CLICK_ESTIMATE = r"""
var norm=function(s){return (s||'').replace(/\s/g,'');};
var els=[].slice.call(document.querySelectorAll('button,input[type=submit],input[type=button],a'));
for(var i=0;i<els.length;i++){
  var t=norm(els[i].textContent||els[i].value||'');
  if(t.indexOf('お見積り')>=0 && els[i].offsetParent!==null){ els[i].click(); return true; }
}
return false;
"""

# 填「訂房者資料」表單（欄位名稱是實際掃描出來的；不會按送出）
JS_FILL_FORM = r"""
var v=arguments[0];
var fire=function(el){ if(!el)return; ['input','change','blur','keyup'].forEach(function(ev){el.dispatchEvent(new Event(ev,{bubbles:true}));}); };
var byId=function(id){return document.getElementById(id);};
var byName=function(n){return document.querySelector('[name="'+n+'"]');};
var setEl=function(el,val){ if(!el) return false; el.value=val; fire(el); return true; };
var pid = (v.payment==='on_site') ? 'payment_on_site' : 'payment_credit_hotepay';
var pay=byId(pid); if(pay){ pay.checked=true; pay.click(); fire(pay); }
setEl(byId('last_name'), v.last);
setEl(byId('first_name'), v.first);
setEl(byId('last_name_kana'), v.lastk);
setEl(byId('first_name_kana'), v.firstk);
setEl(byId('email'), v.email);
setEl(byId('email_confirmation'), v.email);
setEl(byId('birthday'), v.bday);
setEl(byName('birthday'), v.bday);
setEl(byName('zip_code'), v.zip);
var pref=byId('pref'); if(pref){ pref.value=v.pref; fire(pref); }
setEl(byName('address1'), v.addr);
setEl(byName('reserveContact[1][1][tel_number]'), v.tel);
var tt=byId('traffic_type'); if(tt){ tt.value=v.traffic; fire(tt); }
var hh=byId('check_in_hour'); if(hh){ hh.value=v.checkin_h; fire(hh); }
var mm=byId('check_in_minute'); if(mm){ mm.value=v.checkin_m; fire(mm); }
setEl(byId('request'), v.note);
return true;
"""

# 讀取 / 強制設定「市区町村郡/番地」欄位（不含事件觸發的讀取版本）
JS_GET_ADDRESS = "var e=document.querySelector('[name=\"address1\"]'); return e?e.value:null;"
JS_SET_ADDRESS = r"""
var e=document.querySelector('[name="address1"]');
if(!e) return false;
e.value=arguments[0];
['input','change','blur','keyup'].forEach(function(ev){e.dispatchEvent(new Event(ev,{bubbles:true}));});
return true;
"""


def _force_address(driver, addr, tries=8, interval=0.5):
    """填郵便番号後，網站會非同步自動帶出市区町村（例如「台東区台東」），
    晚於我們填表的時間點才蓋掉完整地址，導致「3丁目41-7」被吃掉。
    這裡持續盯著欄位，只要被蓋掉就重填，直到連續兩次都維持我們要的值才罷手。"""
    stable = 0
    for _ in range(tries):
        cur = driver.execute_script(JS_GET_ADDRESS)
        if cur != addr:
            driver.execute_script(JS_SET_ADDRESS, addr)
            stable = 0
        else:
            stable += 1
            if stable >= 2:
                return True
        time.sleep(interval)
    return driver.execute_script(JS_GET_ADDRESS) == addr


def _fill_contact(driver):
    """點下一步→進到訂房者資料頁→填好資料，停在確認前。
    回傳 'filled' / 'blocked'(按不了下一步，多半是未開放) / 'error'。"""
    if not driver.execute_script(JS_CLICK_ESTIMATE):
        return "blocked"
    reached = _poll(driver, "return !!document.getElementById('last_name');", 15)
    if not reached:
        return "blocked"
    time.sleep(1.0)
    try:
        driver.execute_script(JS_FILL_FORM, GUEST)
        _force_address(driver, GUEST["addr"])   # 對抗郵便番号觸發的非同步地址自動帶入
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        return "filled"
    except Exception:
        return "error"


def open_one(cfg):
    """開一個獨立的 Chrome，填好一筆，回傳 (driver, ok, contact)。"""
    profile = tempfile.mkdtemp(prefix="otaki_")
    opts = Options()
    opts.add_argument(f"--user-data-dir={profile}")   # 每個視窗獨立設定檔＝獨立連線
    opts.add_experimental_option("detach", True)
    opts.add_argument("--window-size=1250,1000")
    driver = webdriver.Chrome(options=opts)
    driver.get(BASE + cfg["plan"])
    # 等頁面畫好（日曆表格出現）就繼續，不再死等固定秒數
    _poll(driver,
          "return document.readyState==='complete' && document.querySelectorAll('table td').length>0;",
          LOAD_WAIT)
    driver.execute_script("window.__otaki_ok=undefined;")
    driver.execute_script(JS_FILL, cfg)
    # 等 JS 回報完成旗標就繼續：true=成功、false=沒點到日期，都算「有結果」即停
    ok, end = None, time.time() + 16
    while time.time() < end:
        v = driver.execute_script("return window.__otaki_ok;")
        if v is not None:
            ok = v
            break
        time.sleep(0.2)
    # 第一頁填好了、且開啟自動填表 → 進到訂房者資料頁填好
    contact = None
    if ok and FILL_CONTACT:
        contact = _fill_contact(driver)
    return driver, ok, contact


def _run_one(label, cfg):
    """單一視窗完整流程；回傳 (label, driver_or_None, ok, contact, error_or_None)。"""
    try:
        driver, ok, contact = open_one(cfg)
        return label, driver, ok, contact, None
    except Exception as e:
        return label, None, None, None, e


def _report(label, ok, contact, err):
    if err is not None:
        print(f"   ❌ {label} 開啟失敗：{err}")
        return
    if not ok:
        print(f"   ⚠️ {label} 這筆日期沒點到（可能未開放/月份沒切到），請看該視窗 Console(F12)")
    elif not FILL_CONTACT:
        print(f"   ✅ {label} 第一頁已填好")
    elif contact == "filled":
        print(f"   ✅ {label} 已填到訂房者資料頁（停在確認前，未送出）")
    elif contact == "blocked":
        print(f"   ✅ {label} 第一頁已填好；⚠️ 按不了下一步（多半尚未開放預約，8/1 才開），停在第一頁")
    else:
        print(f"   ✅ {label} 第一頁已填好；⚠️ 進到填表頁但填入時出錯，請手動檢查")


def run(test=False, parallel=False):
    if test:
        jobs = [(f"test#{k}", dict(TEST_BOOKING)) for k in range(TEST_COUNT)]
        print(f"測試模式：用 9/8 方案(917009) 開 {TEST_COUNT} 個視窗，跑完整流程（含填表）")
    else:
        jobs = [(f"idx {i}", BOOKINGS[i]) for i in WHICH_LIST]

    print(f"→ 準備開 {len(jobs)} 個視窗（{'同時開' if parallel else '依序開'}）：")
    for label, cfg in jobs:
        print(f"   {label}: {cfg['name']}（方案 {cfg['plan']}）")
    print()

    drivers = []
    if parallel:
        # 真正同時開：每個視窗各自一條執行緒，幾乎同時啟動/填表，不用排隊等前一個做完
        with ThreadPoolExecutor(max_workers=len(jobs)) as ex:
            futures = {ex.submit(_run_one, label, cfg): label for label, cfg in jobs}
            for fut in as_completed(futures):
                label, driver, ok, contact, err = fut.result()
                if driver is not None:
                    drivers.append(driver)
                _report(label, ok, contact, err)
    else:
        for label, cfg in jobs:
            print(f"→ 開視窗 {label}：{cfg['name']} …")
            _, driver, ok, contact, err = _run_one(label, cfg)
            if driver is not None:
                drivers.append(driver)
            _report(label, ok, contact, err)
            time.sleep(OPEN_GAP)

    print("\n全部視窗已開好並留著。")
    if FILL_CONTACT:
        print("每個視窗應已填到『訂房者資料頁』並停在確認前。請逐一核對後，")
        print("再自行按『予約を確定する』送出。程式不會幫你按送出。")
    else:
        print("請逐一核對右側「現在のご選択内容」，再手動按『確認』→ 填資料 → 付款。")
    print("建議一筆結帳完再處理下一筆。")
    input("\n看完後按 Enter 結束程式（視窗仍會留著）…")


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")   # 避免日文/emoji 在 Windows 終端機編碼崩潰
    except Exception:
        pass
    run(test=("-test" in sys.argv), parallel=("-all" in sys.argv))
