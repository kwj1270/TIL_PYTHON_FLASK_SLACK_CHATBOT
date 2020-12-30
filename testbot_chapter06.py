import slack
import os
from pathlib import Path
from dotenv import load_dotenv
from flask import Flask, request, Response
from slackeventsapi import SlackEventAdapter
import string
from datetime import datetime, timedelta
import time

# 토큰 경로 가져오기
env_path = Path('.') / '.env'
load_dotenv(dotenv_path=env_path)

# 플라스크 실행 
app = Flask(__name__)

# 슬랙 이벤트 어뎁트 토큰 가져와 사용하기
slack_event_adapter = SlackEventAdapter(
    os.environ['SIGNING_SECRET_'], '/slack/events', app)

# 슬랙 토큰 가져와 사용하기 
client = slack.WebClient(token=os.environ['SLACK_TOKEN_'])
# 봇 가져오기
BOT_ID = client.api_call("auth.test")['user_id']

message_counts = {} # 사람당 메시지 몇개 했는지 셈
welcome_messages = {} # 사람당 웰컴 메시지 보냈는지 기록 
BAD_WORDS = ['hmm', 'no', 'tim'] # 금지어 사용

# 웰컴 메시지를 위한 클래스 
class WelcomeMessage:
    START_TEXT = {
        'type': 'section',
        'text': {
            'type': 'mrkdwn', # 마크다운으로 보낸다.  
            'text': (
                'Welcome to this awesome channel! \n\n'
                '*Get started by completing the tasks!*'
            )
        }
    }

    DIVIDER = {'type': 'divider'} 

    def __init__(self, channel):
        self.channel = channel # 어디 채널에서 불렀는지 확인 위해 
        self.icon_emoji = ':robot_face:' # 로봇 얼굴로 보내기
        self.timestamp = '' # 시간 
        self.completed = False # 이모지 넣은 적 없다 --> false

    def get_message(self):
        return {
            'ts': self.timestamp, # 시간 
            'channel': self.channel, # 채널 
            'username': 'Welcome Robot!', # 웰컴 로봇
            'icon_emoji': self.icon_emoji, # 들어온 이모지 
            'blocks': [ # 블록 
                self.START_TEXT, # 웰컴 글  
                self.DIVIDER, # 나누기 선 ---- 이거 말함 
                self._get_reaction_task() # 리액션 태스크 결과 가져오기
            ]
        }

    def _get_reaction_task(self):
        checkmark = ':white_check_mark:' # 체크함 이모지 입력  
        if not self.completed: # 이모지 체크 안했다면 
            checkmark = ':white_large_square:' # 체크 안함 이모지 입력 

        text = f'{checkmark} *React to this message!*' # 입력하세요 글 

        return {'type': 'section', 'text': {'type': 'mrkdwn', 'text': text}} # 추가


def send_welcome_message(channel, user): # 웰컴 메시지 보내기 
    if channel not in welcome_messages: # 채널에 웰컴 메시지 보낸적 없다면 
            welcome_messages[channel] = {} # 채널 추가 

    if user in welcome_messages[channel]: # 유저가 보낸적 있다면 
        return # 다시 보내지 않기 위해서 RETURN만 

    welcome = WelcomeMessage(channel) # 웰컴 메시지 클래스 생성 
    message = welcome.get_message() # 메시지 얻어오기 
    response = client.chat_postMessage(**message) # 보낼 메시지 
    welcome.timestamp = response['ts'] # 시간은 응답 시간으로 변경 

    welcome_messages[channel][user] = welcome # 해당 채널, 사람에게 웰컴 클래스 넣음

@slack_event_adapter.on('message') # 메시지 이벤트 동작시 
def message(payload): # 리퀘스트
    event = payload.get('event', {}) # 이벤트 정보 받아옴 
    channel_id = event.get('channel') # 채널 정보 받아옴
    user_id = event.get('user') # 유저 정보 받아옴 
    text = event.get('text') # 텍스트 정보 받아옴 

    if user_id != None and BOT_ID != user_id: 
        if user_id in message_counts: # 메시지 보낸 적 있다면 
            message_counts[user_id] += 1 # 갯수 증가 
        else:
            message_counts[user_id] = 1 # 보낸적 없다면 1로 초기화 

        if text.lower() == 'start': # start 라는 글이 들어왔다면  
            send_welcome_message(f'@{user_id}', user_id) # 웰컴 시작
        elif check_if_bad_words(text): # 나쁜 글이 들어왔다면 
            ts = event.get('ts') # 현재 시간 넣고 
            client.chat_postMessage( # 메시지 보내기 
                channel=channel_id, thread_ts=ts, text="THAT IS A BAD WORD!")
            # 해당 채널에 다른 스레드로 나쁜 글이다. 라고 댓글달기  
                                                     
@slack_event_adapter.on('reaction_added') # 이모지 이벤트
def reaction(payload): 
    event = payload.get('event', {}) # 이벤트 정보 가져오기 
    channel_id = event.get('item', {}).get('channel') # 채널 가져오기
    user_id = event.get('user') # 유저 가져오기 

    if f'@{user_id}' not in welcome_messages: # 채널에 웰컴 메시지 없다면
        return # 잘못되거나 처리 안해도 되므로 return 만 한다.   

    welcome = welcome_messages[f'@{user_id}'][user_id]  # 기존에 있던 웰컴 메시지 가져온다.
    welcome.completed = True # 이모지 사용을 true로 넣는다.
    welcome.channel = channel_id # 채널 정보 넣는다. 
    message = welcome.get_message() # 메시지 가져온다 
    updated_message = client.chat_update(**message) # 메시지 업데이트
    welcome.timestamp = updated_message['ts'] # 시간 업데이트 

def check_if_bad_words(message): # 나쁜 글자 탐색기 
    msg = message.lower() # 소문자 전환 
    msg = msg.translate(str.maketrans('', '', string.punctuation)) # 번역?

    return any(word in msg for word in BAD_WORDS) # 나쁜 글자 있는지 확인후 리턴 

@app.route('/message-count', methods=['POST'])
def message_count():
    data = request.form
    user_id = data.get('user_id')
    channel_id = data.get('channel_id')
    message_count = message_counts.get(user_id, 0)
    client.chat_postMessage(channel=channel_id, text=f"Message: {message_count}")
    return Response(), 200


if __name__ == "__main__":
    app.run(debug=True)