from bs4 import BeautifulSoup

import datetime
import os

import certifi
import dotenv
import requests


dotenv.load_dotenv()

request_headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/71.0.3578.98 Safari/537.36",
    "Content-Type": "application/x-www-form-urlencoded"
}

logistics_urls = {
    "Customs":      "https://unipass.customs.go.kr:38010/ext/rest/cargCsclPrgsInfoQry/retrieveCargCsclPrgsInfo?crkyCn=%s&blYy=%s&hblNo=%s", # 통관
    "CJ":           "https://trace.cjlogistics.com/next/rest/selectTrackingWaybil.do",                                                      # 대한통운 기본 운송장 정보 조회
    "CJ_status":    "https://trace.cjlogistics.com/next/rest/selectTrackingDetailList.do",                                                  # 대한통운 배송 정보 상세 조회                       
    "Hanjin":       "https://www.hanjin.com/kor/CMS/DeliveryMgr/WaybillResult.do?mCode=MN038&wblnum=%s&schLang=KR",                         # 한진택배
    "KoreaPost":    "https://service.epost.go.kr/trace.RetrieveDomRigiTraceList.comm?sid1=%s",                                              # 우체국택배
    "Logen":        "https://www.ilogen.com/web/personal/trace/%s",                                                                         # 로젠택배
    "Lotte":        "https://www.lotteglogis.com/mobile/reservation/tracking/linkView?InvNo=%s"                                             # 롯데택배
}

def message_logistics(message, room, sender):
    if message.startswith("!택배") or message.startswith("!ㅌㅂ"):
        return message_logistics_main(message)
    if message.startswith("!통관") or message.startswith("!ㅌㄱ"):
        return message_custom_tracker(message)
    return None

def message_custom_tracker(message) -> str:
    try:
        message = message.replace("!통관", "").replace("!ㅌㄱ", "").replace(" ", "")
        key = os.environ["CUSTOM_API_KEY"]
        year = datetime.date.today().year
        url = logistics_urls["Customs"] % (key, year, message)
        result = requests.get(url)
        soup = BeautifulSoup(result.text, "xml")
        name = soup.find("prnm")
        customs_name = soup.find("etprCstm")
        status = soup.find("prgsStts")
        process_time = datetime.datetime.strptime(str(soup.find("prcsDttm").text), "%Y%m%d%H%M%S").strftime("%Y.%m.%d %H:%M:%S")
        return f"/// 관세청 UNIPASS 통관 조회 ///\n\n품명: {name.text}\n입항세관: {customs_name.text}\n통관진행상태: {status.text}\n처리일시: {process_time}"
    except (TypeError, AttributeError):
        return "존재하지 않는 운송장번호이거나 잘못된 형식 혹은 아직 입항하지 않은 화물입니다.\\m사용법: !통관 123456789"

def message_logistics_main(message) -> str:
    common_message = [
        "///택배 운송장조회 사용 방법///\\m사용 예시: !택배[운송장번호]\nex)!택배1234567890\n지원중인 택배사: 우체국택배, 대한통운(CJ, 대통), 로젠택배, 롯데택배, 한진택배",
        "존재하지 않는 운송장번호이거나 잘못된 형식 혹은 아직 수거되지 않은 화물입니다.\\m사용법: !택배[운송장번호]\nex)!택배1234567890\n지원중인 택배사: 우체국택배, 대한통운(CJ, 대통), 로젠택배, 롯데택배, 한진택배"
    ]
    message = message.replace("!택배", "").replace("!ㅌㅂ", "").replace(" ", "")

    if message == "":
        return common_message[0]
    elif not message.isdigit(): # 추후 EMS 등 알파벳이 섞이는 서비스도 조회할거면 비활성화 필요함
        return common_message[1]

    str_message = message_logistics_parser(message)

    if not str_message:
        return common_message[1]

    return str_message

def message_logistics_parser(message) -> str | None:
    logistics = [
        message_logistics_parser_cj,
        message_logistics_parser_hanjin,
        message_logistics_parser_koreapost,
        message_logistics_parser_logen,
        message_logistics_parser_lotte,
    ]

    had_exception = False

    for parser in logistics:
        try:
            result = parser(message)
            if result:
                return result
        except Exception as e:
            had_exception = True
            print(
                f"[message_logistics_parser] Unexpected exception in "
                f"{parser.__name__!r} ({type(e).__name__}): {e}"
            )

    if had_exception: # 5개의 택배사 모두 조회에 실패한 상태에서 오류가 발생한 경우
        return "운송장 조회 중 오류가 발생했습니다.\n잠시 후 다시 시도해주세요."

    return None

def message_logistics_parser_cj(message) -> str | None:
    try:
        post_data = {"wblNo": message}
        logistics_url_info = logistics_urls["CJ"] # 운송장 기본 정보 조회 (받는사람, 보내는사람, 상품명 등)
        request_response = requests.post(logistics_url_info, headers=request_headers, data=post_data)
        if request_response.status_code != 200 or not request_response.json().get("data"): return None
        tracking_data = request_response.json()["data"]
        sndr_nm = (tracking_data.get("sndrNm") or "").strip() or "(정보 없음)"      # 보낸 사람 이름
        rcvr_nm = (tracking_data.get("rcvrNm") or "").strip() or "(정보 없음)"      # 받는 사람 이름
        goods_nm = (tracking_data.get("repGoodsNm") or "").strip() or "(정보 없음)" # 상품명
        qty = (tracking_data.get("qty") or "").strip() or "(정보 없음)"             # 수량
        acpr_nm = (tracking_data.get("acprNm") or "").strip() or "(정보 없음)"      # 인수자
        
        logistics_url_status = logistics_urls["CJ_status"] # 운송장 배송 정보 조회 (배송상태, 처리장소 등)
        request_response = requests.post(logistics_url_status, headers=request_headers, data=post_data)
        status_info = "현재 집하되지 않은 택배입니다."

        if (request_response.status_code == 200 and
            request_response.json().get("data") and
            request_response.json()["data"].get("svcOutList")):
            latest_status = request_response.json()["data"]["svcOutList"][-1]
            status_info = (
                f"처리장소: {(latest_status.get('branNm') or '').strip() or '(정보 없음)'}\n"
                f"전화번호: {(latest_status.get('procBranTelNo') or '').strip() or '(정보 없음)'}\n"
                f"처리일자: {(latest_status.get('workDt') or '').strip() or '(정보 없음)'} "
                f"{(latest_status.get('workHms') or '').strip() or '(정보 없음)'}\n"
                f"상품상태: {(latest_status.get('crgStDnm') or '').strip() or '(정보 없음)'}\n"
                f"상세정보: {(latest_status.get('crgStDcdVal') or '').strip() or '(정보 없음)'}\n"
                f"{'인수자' if '인수자' in ((latest_status.get('patnBranNm') or '').strip() or '(정보 없음)') else '상대장소'}: "
                f"{(latest_status.get('patnBranNm') or '').strip() or '(정보 없음)'}"
            )
            
        return (
            f"/// CJ대한통운 배송조회 ///\n\n"
            f"송화인: {sndr_nm}\n"
            f"수화인: {rcvr_nm}\n"
            f"품목: {goods_nm} (수량: {qty})\n"
            f"인수자: {acpr_nm}\n\n"
            f"{status_info}"
        )
    except (TypeError, IndexError):
        return None

def message_logistics_parser_hanjin(message) -> str | None:
    temp = ""
    try:
        logistics_url = logistics_urls["Hanjin"] % (message)
        request_session = requests.Session()
        request_response = request_session.get(logistics_url, headers=request_headers, verify=certifi.where())
        soup = BeautifulSoup(request_response.text, "html.parser")

        info = soup.select("#delivery-wr > div > div.waybill-tbl > table > tbody > tr")
        if info:
            temp = info[-1].get_text()
        
        infom = temp.split("\n")
        
        if len(infom) > 7 and not infom[7]:
            infom[7] = "(정보 없음)"

        goods_name = soup.select_one("#delivery-wr > div > table > tbody > tr > td:nth-child(1)")
        goods_name = goods_name.get_text().strip() if goods_name else ""

        return f"/// 한진택배 배송조회 ///\n\n상품명: {goods_name}\n날짜: {infom[1]}\n시간: {infom[2]}\n상품위치: {infom[3]}\n배송 진행상황: {infom[5]}\n전화번호: {infom[7]}"

    except (TypeError, IndexError, AttributeError):
        return None

def message_logistics_parser_koreapost(message) -> str | None:
    i = 1
    temp = ""
    try:
        if not message.isdigit(): raise TypeError
        logistics_url = logistics_urls["KoreaPost"] % (message)
        request_session = requests.Session()
        request_response = request_session.get(logistics_url, headers = request_headers, verify=certifi.where())
        soup = BeautifulSoup(request_response.text, "html.parser")
        while True:
            info = soup.select("#processTable > tbody > tr:nth-child(%d)" % i)
            if not info:
                info = soup.select("#processTable > tbody > tr:nth-child(%d)" % int(i-1))
                for tag in info:
                    temp += tag.get_text()
                break
            i = i+1
        infom = temp.split("\n")
        for _ in range(len(infom)):
            if "\t" in infom[_]: infom[_] = infom[_].replace("\t", "")
        if infom[5] == "": infom[5] = "접수"
        if infom[5] == "            ": infom[5] = "배달준비"
        return f"/// 우체국택배 배송조회 ///\n\n날짜: {infom[1]}\n시간: {infom[2]}\n발생국: {infom[3]}\n처리현황: {infom[5]}"
    except (TypeError, IndexError):
        return None

def message_logistics_parser_logen(message) -> str | None:
    i = 1
    temp = ""
    try:
        if not message.isdigit():
            raise TypeError
        logistics_url =  logistics_urls["Logen"] % (message)
        request_session = requests.Session()
        request_response = request_session.get(logistics_url, headers = request_headers, verify=certifi.where())
        soup = BeautifulSoup(request_response.text, "html.parser")
        while True:
            info = soup.select("body > div.contents.personal.tkSearch > section > div > div.tab_container > div > table.data.tkInfo > tbody > tr:nth-child(%d)" % i)
            if not info:
                info = soup.select("body > div.contents.personal.tkSearch > section > div > div.tab_container > div > table.data.tkInfo > tbody > tr:nth-child(%d)" % int(i-1))
                for tag in info:
                    temp += tag.get_text()
                break
            i = i+1
        infom = temp.split("\n")
        for _ in range(len(infom)):
            if "\t" in infom[_]: infom[_] = infom[_].replace("\t", "")
        infom = [v for v in infom if v]
        temp = ""
        if "전달" in infom[3]:
            temp = "\n인수자: " + infom[5]
        elif "배달 준비" in infom[3]:
            temp = "\n배달 예정 시간: " + infom[5]
        return f"/// 로젠택배 배송조회 ///\n\n날짜: {infom[0]}\n사업장: {infom[1]}\n배송상태: {infom[2]}\n배송내용: {infom[3]}" + temp
    except (TypeError, IndexError):
        return None

def message_logistics_parser_lotte(message) -> str | None:
    temp = ""
    try:
        if not message.isdigit():
            raise TypeError
        logistics_url = logistics_urls["Lotte"] % (message)
        request_session = requests.Session()
        request_response = request_session.get(logistics_url, headers = request_headers, verify=certifi.where())
        soup = BeautifulSoup(request_response.text, "html.parser")
        info = soup.find("div", "scroll_date_table")
        for tag in info:
            temp += tag.get_text()
        infom = temp.split("\n")
        for _ in range(len(infom)):
            infom[_] = infom[_].replace("\t", "").replace("\r", "").replace(" ", "").replace(u"\xa0", "")
        infom = [v for v in infom if v]
        infom[6] = infom[6][:10] + " " + infom[6][10:]
        return f"/// 롯데택배 배송조회 ///\n\n단계: {infom[5]}\n시간: {infom[6]}\n현위치: {infom[7]}\n처리현황: {infom[8]}"
    except (TypeError, IndexError):
        return None