from flask import Flask, request, jsonify, make_response
from flask_cors import CORS
import os
import uuid
import requests
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger

app = Flask(__name__)
# CORS 설정 개선 - 모든 리소스에 대해 모든 출처 허용
CORS(app, resources={r"/*": {"origins": "*", "allow_headers": ["Content-Type", "Authorization"]}})

# 간단한 메모리 DB (실제 환경에서는 실제 DB 사용 권장)
shift_records = {}

# Discord 웹훅 URL (환경 변수에서 가져오거나 기본값 사용)
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/1367799493516329030/gnKtt12do5kMGgv4JhsWAkX05-OzhV2FteNEgWTj7E5SMy-uf1bRBaZnrg5dC0-ii7jk")

# 백그라운드 스케줄러 초기화 (daemon=True로 설정하여 메인 스레드 종료 시 자동 종료)
scheduler = BackgroundScheduler(daemon=True)
scheduler.start()

def send_discord_notification(data, message_type="start", custom_message=None):
    """Discord 웹훅으로 알림 보내기"""
    shift_type = data.get('shiftType')
    shift_order = data.get('shiftOrder', '')
    shift_time_range = data.get('shiftTimeRange', '')
    task_type = data.get('taskType', '')
    
    # 기본 임베드 컬러 설정
    embed_color = 0x3498db  # 파란색 (기본)
    
    if message_type == "start":
        title = "🔄 교대 시작 알림"
        description = f"순번 {shift_order}의 교대가 곧 시작됩니다."
        embed_color = 0x2ecc71  # 초록색
    elif message_type == "end":
        title = "🔄 교대 종료 알림"
        description = f"순번 {shift_order}의 교대가 곧 종료됩니다."
        embed_color = 0xe74c3c  # 빨간색
    elif message_type == "recycling":
        title = "♻️ 분리수거 알림"
        description = "분리수거 시간입니다."
        embed_color = 0xf1c40f  # 노란색
    elif message_type == "leave":
        title = "🏠 퇴근 알림"
        description = "퇴근 시간입니다. 수고하셨습니다!"
        embed_color = 0x9b59b6  # 보라색
    elif message_type == "custom":
        title = "📢 교대근무 알림"
        description = custom_message
    
    # Discord 웹훅 페이로드
    payload = {
        "username": "교대근무 알리미",
        "avatar_url": "https://cdn-icons-png.flaticon.com/512/1246/1246351.png",
        "embeds": [
            {
                "title": title,
                "description": description,
                "color": embed_color,
                "timestamp": datetime.now().isoformat()
            }
        ]
    }
    
    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload)
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        print(f"Discord 웹훅 전송 오류: {e}")
        return False

def schedule_shift_notifications(data):
    """교대 시간에 따른 알림 스케줄링"""
    shift_type = data.get('shiftType')
    record_id = data.get('id')
    
    # 현재 날짜
    today = datetime.now().replace(second=0, microsecond=0)
    
    # 알림 시간 목록
    notification_times = []
    
    # 퇴근 알림 설정
    if shift_type == 'morning':
        # 오전근무 - 3시 퇴근
        leave_time = today.replace(hour=3, minute=0)
        if leave_time > datetime.now():
            notification_times.append((leave_time, "leave", "오전근무 퇴근 시간입니다. 수고하셨습니다!"))
        
        # 오전근무는 추가 알림 없음
        
    else:  # 오후근무
        # 오후근무 - 10시 퇴근
        leave_time = today.replace(hour=22, minute=0)  # 24시간 형식으로 22시 = 10시 PM
        if leave_time > datetime.now():
            notification_times.append((leave_time, "leave", "오후근무 퇴근 시간입니다. 수고하셨습니다!"))
        
        shift_order = data.get('shiftOrder')
        shift_time_range = data.get('shiftTimeRange')
        task_type = data.get('taskType')
        
        # 교대 알림 시간 계산
        # 2시부터 4시까지 또는 3시부터 4시까지 선택에 따른 초기 교대 시간
        if shift_time_range == '2-4':
            # 2시부터 4시까지
            start_hour = 2
            if shift_order == '1':
                # 1번: 1:54 시작, 2:34 종료
                start_time = today.replace(hour=1, minute=54)
                end_time = today.replace(hour=2, minute=34)
                notification_times.append((start_time, "start", f"순번 {shift_order}의 교대(1:55~2:35)가 곧 시작됩니다."))
                notification_times.append((end_time, "end", f"순번 {shift_order}의 교대가 곧 종료됩니다."))
            elif shift_order == '2':
                # 2번: 2:34 시작, 3:14 종료
                start_time = today.replace(hour=2, minute=34)
                end_time = today.replace(hour=3, minute=14)
                notification_times.append((start_time, "start", f"순번 {shift_order}의 교대(2:35~3:15)가 곧 시작됩니다."))
                notification_times.append((end_time, "end", f"순번 {shift_order}의 교대가 곧 종료됩니다."))
            elif shift_order == '3':
                # 3번: 3:14 시작, 3:54 종료
                start_time = today.replace(hour=3, minute=14)
                end_time = today.replace(hour=3, minute=54)
                notification_times.append((start_time, "start", f"순번 {shift_order}의 교대(3:15~3:55)가 곧 시작됩니다."))
                notification_times.append((end_time, "end", f"순번 {shift_order}의 교대가 곧 종료됩니다."))
        else:
            # 3시부터 4시까지
            start_hour = 3
            if shift_order == '1':
                # 1번: 2:54 시작, 3:14 종료
                start_time = today.replace(hour=2, minute=54)
                end_time = today.replace(hour=3, minute=14)
                notification_times.append((start_time, "start", f"순번 {shift_order}의 교대(2:55~3:15)가 곧 시작됩니다."))
                notification_times.append((end_time, "end", f"순번 {shift_order}의 교대가 곧 종료됩니다."))
            elif shift_order == '2':
                # 2번: 3:14 시작, 3:34 종료
                start_time = today.replace(hour=3, minute=14)
                end_time = today.replace(hour=3, minute=34)
                notification_times.append((start_time, "start", f"순번 {shift_order}의 교대(3:15~3:35)가 곧 시작됩니다."))
                notification_times.append((end_time, "end", f"순번 {shift_order}의 교대가 곧 종료됩니다."))
            elif shift_order == '3':
                # 3번: 3:34 시작, 3:54 종료
                start_time = today.replace(hour=3, minute=34)
                end_time = today.replace(hour=3, minute=54)
                notification_times.append((start_time, "start", f"순번 {shift_order}의 교대(3:35~3:55)가 곧 시작됩니다."))
                notification_times.append((end_time, "end", f"순번 {shift_order}의 교대가 곧 종료됩니다."))
        
        # 4시부터 10시까지 교대 시간 계산
        # 1-2-3-1-2-3 순서로 1시간씩 교대
        current_hour = 4
        while current_hour < 10:
            for order in ['1', '2', '3']:
                if current_hour >= 10:
                    break
                    
                start_time = today.replace(hour=current_hour-1, minute=54)
                end_time = today.replace(hour=current_hour, minute=54)
                
                # 현재 시간보다 미래인 경우만 알림 스케줄링
                if start_time > datetime.now():
                    notification_times.append((start_time, "start", f"순번 {order}의 교대({current_hour}:00~{current_hour+1}:00)가 곧 시작됩니다."))
                
                if end_time > datetime.now():
                    notification_times.append((end_time, "end", f"순번 {order}의 교대가 곧 종료됩니다."))
                
                current_hour += 1
        
        # 추가 작업 알림 (분리수거)
        if task_type == 'recycling' and (shift_order == '1' or shift_order == '3'):
            recycling_time = today.replace(hour=8, minute=0)
            if recycling_time > datetime.now():
                notification_times.append((recycling_time, "recycling", "분리수거 시간입니다."))
    
    # 알림 스케줄링
    for notification_time, msg_type, custom_msg in notification_times:
        if notification_time > datetime.now():
            job_id = f"{record_id}_{msg_type}_{notification_time.strftime('%H%M')}"
            
            # 기존 작업이 있으면 제거 (수정 요청 시)
            if scheduler.get_job(job_id):
                scheduler.remove_job(job_id)
            
            # 새 작업 스케줄링
            scheduler.add_job(
                send_discord_notification,
                trigger=DateTrigger(run_date=notification_time),
                args=[data, msg_type, custom_msg],
                id=job_id,
                name=f"Shift Notification: {msg_type} at {notification_time.strftime('%H:%M')}"
            )
            print(f"스케줄링됨: {job_id} - {notification_time.strftime('%Y-%m-%d %H:%M')}")

# OPTIONS 요청을 위한 사전 응답 생성
def _build_cors_preflight_response():
    response = make_response()
    response.headers.add("Access-Control-Allow-Origin", "*")
    response.headers.add("Access-Control-Allow-Headers", "Content-Type, Authorization")
    response.headers.add("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
    response.headers.add("Access-Control-Max-Age", "3600")
    return response

# 루트 경로 엔드포인트 추가
@app.route('/', methods=['GET', 'OPTIONS'])
def index():
    """루트 경로 처리"""
    if request.method == 'OPTIONS':
        return _build_cors_preflight_response()
    
    return jsonify({
        'status': 'success',
        'message': '교대근무 알리미 API가 실행 중입니다.',
        'endpoints': ['/shift', '/shift/<record_id>', '/shifts']
    })

@app.route('/shift', methods=['POST', 'OPTIONS'])
def handle_shift():
    # OPTIONS 요청 처리
    if request.method == 'OPTIONS':
        return _build_cors_preflight_response()
        
    try:
        # 요청 데이터 가져오기
        data = request.json
        
        # 필수 필드 검증
        required_fields = ['shiftType']
        if not all(field in data for field in required_fields):
            return jsonify({
                'status': 'error',
                'message': '필수 필드가 누락되었습니다'
            }), 400
        
        # 현재 시간 기록
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 수정 요청인지 확인
        request_id = data.get('id')
        is_update = False
        
        if request_id and request_id in shift_records:
            # 기존 레코드 업데이트
            shift_records[request_id].update({
                'shiftType': data.get('shiftType'),
                'shiftOrder': data.get('shiftOrder'),
                'shiftTimeRange': data.get('shiftTimeRange'),
                'taskType': data.get('taskType'),
                'updated_at': now
            })
            is_update = True
            record = shift_records[request_id]
        else:
            # 새 레코드 생성
            record_id = str(uuid.uuid4())
            shift_records[record_id] = {
                'id': record_id,
                'shiftType': data.get('shiftType'),
                'shiftOrder': data.get('shiftOrder'),
                'shiftTimeRange': data.get('shiftTimeRange'),
                'taskType': data.get('taskType'),
                'created_at': now,
                'updated_at': now
            }
            request_id = record_id
            record = shift_records[record_id]
        
        # 교대 알림 스케줄링
        data['id'] = request_id  # ID 추가
        schedule_shift_notifications(data)
        
        # 즉시 알림 보내기 (근무 시작/수정)
        if is_update:
            custom_message = f"근무 정보가 수정되었습니다: 순번 {data.get('shiftOrder')}, 시간대 {data.get('shiftTimeRange')}"
            if data.get('shiftOrder') in ['1', '3'] and data.get('taskType'):
                task_name = "분리수거" if data.get('taskType') == "recycling" else "화장실청소"
                custom_message += f", 추가 작업: {task_name}"
            notification_sent = send_discord_notification(data, "custom", custom_message)
        else:
            custom_message = f"근무가 시작되었습니다: 순번 {data.get('shiftOrder')}, 시간대 {data.get('shiftTimeRange')}"
            if data.get('shiftOrder') in ['1', '3'] and data.get('taskType'):
                task_name = "분리수거" if data.get('taskType') == "recycling" else "화장실청소"
                custom_message += f", 추가 작업: {task_name}"
            notification_sent = send_discord_notification(data, "custom", custom_message)
        
        # 응답 생성
        response_data = {
            'status': 'success',
            'message': '근무 정보가 수정되었습니다' if is_update else '근무가 시작되었습니다',
            'data': record,
            'id': request_id,
            'notification_sent': notification_sent,
            'notifications_scheduled': True
        }
        
        return jsonify(response_data), 200
    
    except Exception as e:
        # 오류 처리
        return jsonify({
            'status': 'error',
            'message': f'서버 오류: {str(e)}'
        }), 500

@app.route('/shift/<record_id>', methods=['GET', 'OPTIONS'])
def get_shift(record_id):
    """특정 근무 기록 조회"""
    if request.method == 'OPTIONS':
        return _build_cors_preflight_response()
        
    if record_id in shift_records:
        return jsonify({
            'status': 'success',
            'data': shift_records[record_id]
        }), 200
    else:
        return jsonify({
            'status': 'error',
            'message': '해당 ID의 근무 기록을 찾을 수 없습니다'
        }), 404

@app.route('/shifts', methods=['GET', 'OPTIONS'])
def get_all_shifts():
    """모든 근무 기록 조회"""
    if request.method == 'OPTIONS':
        return _build_cors_preflight_response()
        
    return jsonify({
        'status': 'success',
        'data': list(shift_records.values())
    }), 200

# 서버 종료 시 스케줄러도 종료
@app.before_request
def init_scheduler():
    if not scheduler.running:
        scheduler.start()

@app.teardown_appcontext
def shutdown_scheduler(exception=None):
    pass  # 종료 시 스케줄러 셧다운을 비활성화 (daemon=True로 설정했기 때문)

# Railway와 같은 클라우드 서비스 배포를 위한 포트 설정
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
