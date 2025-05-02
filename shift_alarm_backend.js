const express = require('express');
const cors = require('cors');
const axios = require('axios');
const uuid = require('uuid');
const schedule = require('node-schedule');
const { DateTime } = require('luxon');  // 시간 관련 처리

const app = express();
const DISCORD_WEBHOOK_URL = process.env.DISCORD_WEBHOOK_URL || "https://discord.com/api/webhooks/1367799493516329030/gnKtt12do5kMGgv4JhsWAkX05-OzhV2FteNEgWTj7E5SMy-uf1bRBaZnrg5dC0-ii7jk";

// CORS 설정
app.use(cors());
app.use(express.json());  // JSON 요청 본문 파싱

// 간단한 메모리 DB (실제 환경에서는 실제 DB 사용 권장)
let shiftRecords = {};

// Discord 알림 함수
function sendDiscordNotification(data, messageType = 'start', customMessage = null) {
    const shiftType = data.shiftType;
    const shiftOrder = data.shiftOrder || '';
    const shiftTimeRange = data.shiftTimeRange || '';
    const taskType = data.taskType || '';

    let title = '';
    let description = '';
    let embedColor = 0x3498db; // 기본 파란색

    if (messageType === 'start') {
        title = '🔄 교대 시작 알림';
        description = `순번 ${shiftOrder}의 교대가 곧 시작됩니다.`;
        embedColor = 0x2ecc71;  // 초록색
    } else if (messageType === 'end') {
        title = '🔄 교대 종료 알림';
        description = `순번 ${shiftOrder}의 교대가 곧 종료됩니다.`;
        embedColor = 0xe74c3c;  // 빨간색
    } else if (messageType === 'recycling') {
        title = '♻️ 분리수거 알림';
        description = '분리수거 시간입니다.';
        embedColor = 0xf1c40f;  // 노란색
    } else if (messageType === 'leave') {
        title = '🏠 퇴근 알림';
        description = '퇴근 시간입니다. 수고하셨습니다!';
        embedColor = 0x9b59b6;  // 보라색
    } else if (messageType === 'custom') {
        title = '📢 교대근무 알림';
        description = customMessage;
    }

    const payload = {
        username: '교대근무 알리미',
        avatar_url: 'https://cdn-icons-png.flaticon.com/512/1246/1246351.png',
        embeds: [
            {
                title: title,
                description: description,
                color: embedColor,
                timestamp: DateTime.now().toISO(),
            },
        ],
    };

    axios.post(DISCORD_WEBHOOK_URL, payload).catch((error) => {
        console.error('Discord 웹훅 전송 오류:', error);
    });
}

// 교대 시간에 따른 알림 스케줄링
function scheduleShiftNotifications(data) {
    const shiftType = data.shiftType;
    const recordId = data.id;
    const today = DateTime.local().startOf('day');

    let notificationTimes = [];

    // 퇴근 알림 설정
    if (shiftType === 'morning') {
        // 오전 근무 - 3시 퇴근
        let leaveTime = today.set({ hour: 3, minute: 0 });
        if (leaveTime > DateTime.local()) {
            notificationTimes.push({ time: leaveTime, type: 'leave', message: '오전근무 퇴근 시간입니다. 수고하셨습니다!' });
        }
    } else {  // 오후 근무
        let leaveTime = today.set({ hour: 22, minute: 0 });
        if (leaveTime > DateTime.local()) {
            notificationTimes.push({ time: leaveTime, type: 'leave', message: '오후근무 퇴근 시간입니다. 수고하셨습니다!' });
        }
    }

    // 교대 알림 시간 계산 (여기서는 예시로 1시간 간격으로 교대)
    for (let hour = 4; hour < 10; hour++) {
        for (let order of ['1', '2', '3']) {
            let startTime = today.set({ hour: hour, minute: 0 });
            let endTime = today.set({ hour: hour + 1, minute: 0 });

            if (startTime > DateTime.local()) {
                notificationTimes.push({ time: startTime, type: 'start', message: `순번 ${order}의 교대가 곧 시작됩니다.` });
            }
            if (endTime > DateTime.local()) {
                notificationTimes.push({ time: endTime, type: 'end', message: `순번 ${order}의 교대가 곧 종료됩니다.` });
            }
        }
    }

    // 분리수거 작업 알림
    if (data.taskType === 'recycling') {
        let recyclingTime = today.set({ hour: 8, minute: 0 });
        if (recyclingTime > DateTime.local()) {
            notificationTimes.push({ time: recyclingTime, type: 'recycling', message: '분리수거 시간입니다.' });
        }
    }

    // 알림 스케줄링
    notificationTimes.forEach(({ time, type, message }) => {
        if (time > DateTime.local()) {
            schedule.scheduleJob(`${recordId}_${type}_${time.toFormat('HHmm')}`, time.toJSDate(), () => {
                sendDiscordNotification(data, type, message);
            });
        }
    });
}

// 라우트 설정
app.post('/shift', (req, res) => {
    const data = req.body;
    const now = DateTime.local().toFormat('yyyy-MM-dd HH:mm:ss');

    // 필수 필드 검증
    if (!data.shiftType) {
        return res.status(400).json({
            status: 'error',
            message: '필수 필드가 누락되었습니다.',
        });
    }

    const requestId = data.id || uuid.v4();
    let record = shiftRecords[requestId];

    if (!record) {
        // 새 레코드 생성
        record = {
            id: requestId,
            shiftType: data.shiftType,
            shiftOrder: data.shiftOrder,
            shiftTimeRange: data.shiftTimeRange,
            taskType: data.taskType,
            createdAt: now,
            updatedAt: now,
        };
        shiftRecords[requestId] = record;
    } else {
        // 기존 레코드 업데이트
        record.updatedAt = now;
        record.shiftType = data.shiftType;
        record.shiftOrder = data.shiftOrder;
        record.shiftTimeRange = data.shiftTimeRange;
        record.taskType = data.taskType;
    }

    // 교대 알림 스케줄링
    scheduleShiftNotifications(record);

    // 응답
    res.json({
        status: 'success',
        message: '근무 정보가 수정되었습니다.',
        data: record,
    });
});

app.get('/shift/:id', (req, res) => {
    const { id } = req.params;

    if (shiftRecords[id]) {
        res.json({
            status: 'success',
            data: shiftRecords[id],
        });
    } else {
        res.status(404).json({
            status: 'error',
            message: '해당 ID의 근무 기록을 찾을 수 없습니다.',
        });
    }
});

app.get('/shifts', (req, res) => {
    res.json({
        status: 'success',
        data: Object.values(shiftRecords),
    });
});

// 서버 시작
const PORT = process.env.PORT || 5000;
app.listen(PORT, () => {
    console.log(`서버가 ${PORT}번 포트에서 실행 중입니다.`);
});
