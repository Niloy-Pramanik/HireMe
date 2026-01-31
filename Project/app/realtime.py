from flask_socketio import emit, join_room, leave_room
from flask import session, request
from datetime import datetime
from extensions import db, socketio
from models import User, InterviewParticipant
from collections import defaultdict

# Track interview participants
INTERVIEW_PARTICIPANTS = defaultdict(dict)  # room_id -> { sid: user_info }
SID_TO_INTERVIEW_ROOM = {}  # sid -> room_id

@socketio.on('connect')
def on_connect():
    print(f'Client connected: {request.sid}')

@socketio.on('join_interview')
def on_join_interview(data):
    room_id = str(data['room'])
    room_code = data.get('room_code', '')
    user_role = data.get('role', 'participant')
    
    # Join the socket.io room
    join_room(room_id)
    
    # Get user info from session
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
        if user:
            user_info = {
                'username': f"{user.first_name} {user.last_name}",
                'role': user_role,
                'user_id': user.id,
                'sid': request.sid
            }
            
            # Track participant
            INTERVIEW_PARTICIPANTS[room_id][request.sid] = user_info
            SID_TO_INTERVIEW_ROOM[request.sid] = room_id
            
            print(f'User {user_info["username"]} joined room {room_id}')
            
            # Update participant status in database
            try:
                participant = InterviewParticipant.query.filter_by(
                    room_id=int(room_id),
                    user_id=user.id
                ).first()
                if participant:
                    participant.joined_at = datetime.utcnow()
                    participant.is_active = True
                    db.session.commit()
            except Exception as e:
                print(f'Error updating participant status: {e}')
            
            # Send existing participants to the joiner (excluding self)
            others = [
                {'sid': sid, 'username': info['username'], 'role': info['role']}
                for sid, info in INTERVIEW_PARTICIPANTS[room_id].items()
                if sid != request.sid
            ]
            emit('participants', {'participants': others}, to=request.sid)
            
            # Notify others in room about new participant
            emit('user_joined', {
                'sid': request.sid,
                'username': user_info['username'],
                'role': user_info['role']
            }, room=room_id, include_self=False)

@socketio.on('leave_interview')
def on_leave_interview(data):
    room_id = str(data.get('room', ''))
    
    if not room_id:
        room_id = SID_TO_INTERVIEW_ROOM.get(request.sid)
    
    if room_id:
        leave_room(room_id)
        
        # Cleanup tracking
        user_info = INTERVIEW_PARTICIPANTS[room_id].pop(request.sid, None)
        SID_TO_INTERVIEW_ROOM.pop(request.sid, None)
        
        if user_info:
            print(f'User {user_info["username"]} left room {room_id}')
            
            # Update participant status in database
            try:
                if 'user_id' in user_info:
                    participant = InterviewParticipant.query.filter_by(
                        room_id=int(room_id), 
                        user_id=user_info['user_id']
                    ).first()
                    if participant:
                        participant.left_at = datetime.utcnow()
                        participant.is_active = False
                        db.session.commit()
            except Exception as e:
                print(f'Error updating participant status: {e}')
            
            # Notify others
            emit('user_left', {
                'sid': request.sid, 
                'username': user_info['username']
            }, room=room_id)

@socketio.on('disconnect')
def on_interview_disconnect():
    sid = request.sid
    room_id = SID_TO_INTERVIEW_ROOM.pop(sid, None)
    
    if room_id:
        user_info = INTERVIEW_PARTICIPANTS[room_id].pop(sid, None)
        
        if user_info:
            print(f'User {user_info["username"]} disconnected from room {room_id}')
            
            # Notify others
            emit('user_left', {
                'sid': sid, 
                'username': user_info['username']
            }, room=room_id)

# ===================== WebRTC Signaling Events =====================

@socketio.on('offer')
def on_interview_offer(data):
    """Relay WebRTC offer to specific peer"""
    to_sid = data.get('to')
    offer = data.get('offer')
    
    if to_sid and offer:
        print(f'Relaying offer from {request.sid} to {to_sid}')
        emit('offer', {
            'offer': offer,
            'from': request.sid
        }, to=to_sid)

@socketio.on('answer')
def on_interview_answer(data):
    """Relay WebRTC answer to specific peer"""
    to_sid = data.get('to')
    answer = data.get('answer')
    
    if to_sid and answer:
        print(f'Relaying answer from {request.sid} to {to_sid}')
        emit('answer', {
            'answer': answer,
            'from': request.sid
        }, to=to_sid)

@socketio.on('ice_candidate')
def on_interview_ice_candidate(data):
    """Relay ICE candidate to specific peer"""
    to_sid = data.get('to')
    candidate = data.get('candidate')
    
    if to_sid and candidate:
        emit('ice_candidate', {
            'candidate': candidate,
            'from': request.sid
        }, to=to_sid)

# ===================== Chat Events =====================

@socketio.on('chat_message')
def on_chat_message(data):
    """Broadcast chat message to all participants in room"""
    room_id = str(data.get('room', ''))
    message = data.get('message', '')
    
    if not room_id:
        room_id = SID_TO_INTERVIEW_ROOM.get(request.sid)
    
    if room_id and message:
        user_info = INTERVIEW_PARTICIPANTS.get(room_id, {}).get(request.sid, {})
        username = user_info.get('username', 'Unknown')
        
        print(f'Chat message from {username} in room {room_id}: {message[:50]}...')
        
        emit('chat_message', {
            'message': message,
            'username': username,
            'from': request.sid,
            'timestamp': datetime.utcnow().isoformat()
        }, room=room_id, include_self=False)

# ===================== Screen Sharing Events =====================

@socketio.on('screen_share_started')
def on_screen_share_started(data):
    """Notify others when user starts screen sharing"""
    room_id = str(data.get('room', ''))
    
    if not room_id:
        room_id = SID_TO_INTERVIEW_ROOM.get(request.sid)
    
    if room_id:
        user_info = INTERVIEW_PARTICIPANTS.get(room_id, {}).get(request.sid, {})
        username = user_info.get('username', 'Unknown')
        
        print(f'{username} started screen sharing in room {room_id}')
        
        emit('peer_screen_share_started', {
            'from': request.sid,
            'username': username
        }, room=room_id, include_self=False)

@socketio.on('screen_share_stopped')
def on_screen_share_stopped(data):
    """Notify others when user stops screen sharing"""
    room_id = str(data.get('room', ''))
    
    if not room_id:
        room_id = SID_TO_INTERVIEW_ROOM.get(request.sid)
    
    if room_id:
        user_info = INTERVIEW_PARTICIPANTS.get(room_id, {}).get(request.sid, {})
        username = user_info.get('username', 'Unknown')
        
        print(f'{username} stopped screen sharing in room {room_id}')
        
        emit('peer_screen_share_stopped', {
            'from': request.sid,
            'username': username
        }, room=room_id, include_self=False)

# ===================== Code Editor Events (Optional) =====================

@socketio.on('code_change')
def on_code_change(data):
    """Broadcast code changes to all participants"""
    room_id = str(data.get('room', ''))
    
    if not room_id:
        room_id = SID_TO_INTERVIEW_ROOM.get(request.sid)
    
    if room_id:
        emit('code_updated', {
            'code': data.get('code', ''),
            'language': data.get('language', 'javascript'),
            'from': request.sid
        }, room=room_id, include_self=False)
