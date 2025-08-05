import requests

url = "http://localhost:3000/predict"

payload = {
    "payload": {
        "text": "8월 4일, 월요일. 테스트 문장입니다.",
        "voice_name": "sample_female"
    },
    "auth_data": {
        "signature": "dummy",
        "cost": 0,
        "endpoint": "dummy",
        "reqnum": 0,
        "url": url
        
    }
}

res = requests.post(url, json=payload)
print(res.status_code)
try:
    print(res.json())
except Exception:
    print(res.text)