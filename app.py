from flask import Flask, render_template, request, redirect, url_for, session

app = Flask(__name__)

# session을 사용하려면 secret_key가 필요해.
# 지금은 포트폴리오/실습용이라 간단하게 작성한 값이야.
app.secret_key = "oasecure-secret-key"


def is_logged_in():
    return session.get("is_admin")


@app.route("/")
def index():
    # 이미 로그인한 상태라면 관리자 페이지로 이동
    if is_logged_in():
        return redirect(url_for("admin"))

    return render_template("index.html")


@app.route("/login", methods=["POST"])
def login():
    username = request.form.get("username")
    password = request.form.get("password")

    # 포트폴리오/실습용 하드코딩 로그인
    if username == "admin" and password == "1234":
        session["is_admin"] = True
        session["username"] = username
        return redirect(url_for("admin"))

    error = "아이디 또는 비밀번호가 올바르지 않습니다."
    return render_template("index.html", error=error)


@app.route("/admin")
def admin():
    # 로그인하지 않고 /admin에 직접 들어오면 로그인 페이지로 이동
    if not is_logged_in():
        return redirect(url_for("index"))

    # Overview 카드용 샘플 데이터
    overview_stats = {
        "total_events": 128,
        "blocked": 12,
        "masked": 38,
        "warned": 17,
        "active_users": 24
    }

    # 이벤트별 통계 샘플 데이터
    event_stats = {
        "Allowed": 61,
        "Blocked": 12,
        "Masked": 38,
        "Warned": 17
    }

    # 사용자별 통계 샘플 데이터
    user_stats = {
        "admin": 32,
        "user01": 28,
        "user02": 21,
        "user03": 18,
        "guest": 9
    }

    # 기간별 통계 샘플 데이터
    period_stats = {
        "2026-05-20": 14,
        "2026-05-21": 18,
        "2026-05-22": 20,
        "2026-05-23": 16,
        "2026-05-24": 24,
        "2026-05-25": 17,
        "2026-05-26": 19
    }

    return render_template(
        "admin.html",
        overview_stats=overview_stats,
        event_stats=event_stats,
        user_stats=user_stats,
        period_stats=period_stats
    )


@app.route("/events")
def events():
    # 로그인하지 않고 /events에 직접 들어오면 로그인 페이지로 이동
    if not is_logged_in():
        return redirect(url_for("index"))

    # 이벤트 관리 페이지 샘플 데이터
    event_list = [
        {
            "id": 1,
            "event_type": "API Key 탐지",
            "user": "user01",
            "result": "Blocked",
            "risk": "High",
            "created_at": "2026-05-26 09:15"
        },
        {
            "id": 2,
            "event_type": "개인정보 탐지",
            "user": "user02",
            "result": "Masked",
            "risk": "Medium",
            "created_at": "2026-05-26 10:02"
        },
        {
            "id": 3,
            "event_type": "프롬프트 정책 위반",
            "user": "admin",
            "result": "Warned",
            "risk": "Medium",
            "created_at": "2026-05-26 11:40"
        },
        {
            "id": 4,
            "event_type": "일반 요청",
            "user": "guest",
            "result": "Allowed",
            "risk": "Low",
            "created_at": "2026-05-26 13:08"
        },
        {
            "id": 5,
            "event_type": "DB 접속 문자열 탐지",
            "user": "user03",
            "result": "Blocked",
            "risk": "High",
            "created_at": "2026-05-26 14:21"
        }
    ]

    return render_template("events.html", event_list=event_list)

@app.route("/events/detail/<risk>")
def event_detail(risk):
    all_events = [
        {
            "event_id": "EVT-20260529-001",
            "time": "10:32",
            "user": "김OO",
            "service": "ChatGPT",
            "action": "Block",
            "risk_level": "Critical",
            "risk_class": "critical",
            "risk_score": 95,
            "summary": "API Key 형태의 민감정보 탐지",
            "detector": "secret / api_key",
            "prompt_hash": "ph_9a31",
            "platform": "Web"
        },
        {
            "event_id": "EVT-20260529-002",
            "time": "10:28",
            "user": "박OO",
            "service": "ChatGPT",
            "action": "Mask",
            "risk_level": "High",
            "risk_class": "high",
            "risk_score": 72,
            "summary": "전화번호 형태의 개인정보 탐지",
            "detector": "pii / phone",
            "prompt_hash": "ph_7d2a",
            "platform": "Web"
        },
        {
            "event_id": "EVT-20260529-003",
            "time": "10:15",
            "user": "이OO",
            "service": "ChatGPT",
            "action": "Warn",
            "risk_level": "Medium",
            "risk_class": "medium",
            "risk_score": 48,
            "summary": "계약 관련 업무기밀 키워드 탐지",
            "detector": "business_context / contract",
            "prompt_hash": "ph_3c81",
            "platform": "Web"
        }
    ]

    if risk == "all":
        filtered_events = all_events
        title = "전체 이벤트 상세보기"
    else:
        filtered_events = [
            event for event in all_events
            if event["risk_class"] == risk
        ]

        title_map = {
            "critical": "Critical 이벤트 상세보기",
            "high": "High 이벤트 상세보기",
            "medium": "Medium 이벤트 상세보기"
        }

        title = title_map.get(risk, "이벤트 상세보기")

    return render_template(
        "event_detail.html",
        events=filtered_events,
        title=title
    )


@app.route("/users")
def users():
    # 로그인하지 않고 /users에 직접 들어오면 로그인 페이지로 이동
    if not is_logged_in():
        return redirect(url_for("index"))

    # 사용자 관리 페이지 샘플 데이터
    user_list = [
        {
            "id": 1,
            "username": "admin",
            "email": "admin@oasecure.com",
            "role": "ADMIN",
            "status": "Active",
            "last_login": "2026-05-26 09:00"
        },
        {
            "id": 2,
            "username": "user01",
            "email": "user01@oasecure.com",
            "role": "USER",
            "status": "Active",
            "last_login": "2026-05-26 10:15"
        },
        {
            "id": 3,
            "username": "user02",
            "email": "user02@oasecure.com",
            "role": "USER",
            "status": "Active",
            "last_login": "2026-05-25 18:30"
        },
        {
            "id": 4,
            "username": "user03",
            "email": "user03@oasecure.com",
            "role": "USER",
            "status": "Locked",
            "last_login": "2026-05-24 16:45"
        },
        {
            "id": 5,
            "username": "guest",
            "email": "guest@oasecure.com",
            "role": "GUEST",
            "status": "Inactive",
            "last_login": "2026-05-20 12:10"
        }
    ]

    return render_template("users.html", user_list=user_list)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)