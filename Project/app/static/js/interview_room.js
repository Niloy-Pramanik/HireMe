/**
 * Google Meet-like Interview Room - WebRTC Implementation
 * Supports multiple participants, chat, screen sharing
 */

(function() {
'use strict';

// Always allow fresh initialization
if (window._MeetingRoomLoaded && window.meetingRoom) {
    console.log('Cleaning up existing meeting room...');
    try {
        if (window.meetingRoom.localStream) {
            window.meetingRoom.localStream.getTracks().forEach(function(t) { t.stop(); });
        }
        if (window.meetingRoom.screenStream) {
            window.meetingRoom.screenStream.getTracks().forEach(function(t) { t.stop(); });
        }
        if (window.meetingRoom.socket) {
            window.meetingRoom.socket.disconnect();
        }
        if (window.meetingRoom.peers) {
            window.meetingRoom.peers.forEach(function(pc) { pc.close(); });
            window.meetingRoom.peers.clear();
        }
        if (window.meetingRoom.remoteStreams) {
            window.meetingRoom.remoteStreams.forEach(function(stream) {
                stream.getTracks().forEach(function(t) { t.stop(); });
            });
            window.meetingRoom.remoteStreams.clear();
        }
        // Clear video grid
        var existingGrid = document.getElementById('videoGrid');
        if (existingGrid) {
            existingGrid.innerHTML = '';
        }
    } catch(e) { console.log('Cleanup error:', e); }
    window.meetingRoom = null;
}
window._MeetingRoomLoaded = true;

function MeetingRoom(config) {
    var self = this;
    
    this.roomId = config.roomId;
    this.roomCode = config.roomCode;
    this.userId = config.userId;
    this.username = config.username;
    this.userRole = config.userRole;
    
    // Media streams
    this.localStream = null;
    this.screenStream = null;
    
    // Peer connections: peerId -> RTCPeerConnection
    this.peers = new Map();
    
    // Remote streams: peerId -> MediaStream
    this.remoteStreams = new Map();
    
    // Participant info: peerId -> { username, role }
    this.participants = new Map();
    
    // State
    this.isAudioEnabled = true;
    this.isVideoEnabled = true;
    this.isScreenSharing = false;
    this.isChatOpen = false;
    this.isParticipantsOpen = false;
    
    // Socket connection
    this.socket = null;
    
    // ICE servers configuration
    this.iceServers = {
        iceServers: [
            { urls: 'stun:stun.l.google.com:19302' },
            { urls: 'stun:stun1.l.google.com:19302' },
            { urls: 'stun:stun2.l.google.com:19302' },
            { urls: 'stun:stun3.l.google.com:19302' },
            { urls: 'stun:stun4.l.google.com:19302' }
        ]
    };
    
    // Pending ICE candidates
    this.pendingCandidates = new Map();
    
    // Chat
    this.messages = [];
    this.unreadCount = 0;
    
    // Setup cleanup on page unload
    var self = this;
    window.addEventListener('beforeunload', function() {
        self.cleanup();
    });
    
    // Initialize
    this.init();
}

MeetingRoom.prototype.cleanup = function() {
    console.log('Cleaning up meeting room...');
    try {
        if (this.localStream) {
            this.localStream.getTracks().forEach(function(t) { t.stop(); });
            this.localStream = null;
        }
        if (this.screenStream) {
            this.screenStream.getTracks().forEach(function(t) { t.stop(); });
            this.screenStream = null;
        }
        if (this.socket) {
            this.socket.emit('leave_interview', { room: this.roomId });
            this.socket.disconnect();
            this.socket = null;
        }
        if (this.peers) {
            this.peers.forEach(function(pc) { pc.close(); });
            this.peers.clear();
        }
        if (this.remoteStreams) {
            this.remoteStreams.forEach(function(stream) {
                stream.getTracks().forEach(function(t) { t.stop(); });
            });
            this.remoteStreams.clear();
        }
        if (this.participants) {
            this.participants.clear();
        }
        // Clear pending timers
        if (this.updateTileTimers) {
            this.updateTileTimers.forEach(function(timer) {
                clearTimeout(timer);
            });
            this.updateTileTimers.clear();
        }
        // Clear video grid
        var videoGrid = document.getElementById('videoGrid');
        if (videoGrid) {
            videoGrid.innerHTML = '';
        }
    } catch(e) { console.log('Cleanup error:', e); }
};

MeetingRoom.prototype.init = function() {
    var self = this;
    console.log('Initializing Meeting Room...');
    
    // Clear video grid first to prevent duplicates
    var videoGrid = document.getElementById('videoGrid');
    if (videoGrid) {
        console.log('Clearing video grid on init');
        videoGrid.innerHTML = '';
    }
    
    this.getLocalMedia().then(function() {
        self.connectSocket();
        self.setupUIListeners();
        self.updateParticipantCount();
        console.log('Meeting Room initialized successfully');
    }).catch(function(error) {
        console.error('Failed to initialize meeting room:', error);
        self.showError('Failed to initialize meeting. Please check your camera/microphone permissions.');
    });
};

MeetingRoom.prototype.getLocalMedia = function() {
    var self = this;
    
    return navigator.mediaDevices.getUserMedia({
        video: {
            width: { ideal: 1280, max: 1920 },
            height: { ideal: 720, max: 1080 },
            facingMode: 'user'
        },
        audio: {
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: true
        }
    }).then(function(stream) {
        self.localStream = stream;
        
        var localVideo = document.getElementById('localVideo');
        if (localVideo) {
            localVideo.srcObject = stream;
            localVideo.muted = true;
        }
        
        console.log('Local media acquired successfully');
        self.addVideoTile('local', self.username + ' (You)', stream, true);
        
    }).catch(function(error) {
        console.error('Error getting local media:', error);
        
        return navigator.mediaDevices.getUserMedia({
            video: false,
            audio: true
        }).then(function(stream) {
            self.localStream = stream;
            console.log('Audio-only mode');
            self.isVideoEnabled = false;
            self.addVideoTile('local', self.username + ' (You)', null, true);
        });
    });
};

MeetingRoom.prototype.connectSocket = function() {
    var self = this;
    
    this.socket = io({
        transports: ['websocket', 'polling']
    });
    
    this.socket.on('connect', function() {
        console.log('Socket connected:', self.socket.id);
        
        self.socket.emit('join_interview', {
            room: self.roomId,
            room_code: self.roomCode,
            role: self.userRole
        });
    });
    
    this.socket.on('disconnect', function() {
        console.log('Socket disconnected');
        self.showNotification('Connection lost. Reconnecting...');
    });
    
    this.socket.on('participants', function(data) {
        console.log('Existing participants:', data.participants);
        data.participants.forEach(function(p) {
            if (p.sid !== self.socket.id) {
                self.participants.set(p.sid, { 
                    username: p.username, 
                    role: p.role 
                });
                console.log('Waiting for offer from existing participant:', p.sid);
            }
        });
        self.updateParticipantCount();
        self.updateParticipantsList();
        
        // Update candidate-main styling if there are existing participants
        setTimeout(function() {
            self.updateAllTilesForCandidateMain();
        }, 500);
    });
    
    this.socket.on('user_joined', function(data) {
        console.log('User joined:', data);
        if (data.sid !== self.socket.id) {
            self.participants.set(data.sid, { 
                username: data.username, 
                role: data.role 
            });
            self.showNotification(data.username + ' joined the meeting');
            self.updateParticipantCount();
            self.updateParticipantsList();
            
            console.log('Creating peer connection for new participant:', data.sid);
            self.createPeerConnection(data.sid, true);
            
            // Update candidate-main styling for all tiles
            setTimeout(function() {
                self.updateAllTilesForCandidateMain();
            }, 500);
        }
    });
    
    this.socket.on('user_left', function(data) {
        console.log('User left:', data);
        self.handlePeerDisconnect(data.sid);
        self.showNotification(data.username + ' left the meeting');
        
        // Update candidate-main styling for remaining tiles
        setTimeout(function() {
            self.updateAllTilesForCandidateMain();
        }, 300);
    });
    
    this.socket.on('offer', function(data) {
        console.log('Received offer from:', data.from);
        self.handleOffer(data.from, data.offer);
    });
    
    this.socket.on('answer', function(data) {
        console.log('Received answer from:', data.from);
        self.handleAnswer(data.from, data.answer);
    });
    
    this.socket.on('ice_candidate', function(data) {
        self.handleIceCandidate(data.from, data.candidate);
    });
    
    this.socket.on('chat_message', function(data) {
        self.addChatMessage(data.username, data.message, data.timestamp, false);
    });
    
    // Screen sharing events
    this.socket.on('peer_screen_share_started', function(data) {
        console.log('Peer started screen sharing:', data.from);
        var participant = self.participants.get(data.from);
        if (participant) {
            participant.isScreenSharing = true;
            self.showNotification(data.username + ' started sharing screen');
        }
    });
    
    this.socket.on('peer_screen_share_stopped', function(data) {
        console.log('Peer stopped screen sharing:', data.from);
        var participant = self.participants.get(data.from);
        if (participant) {
            participant.isScreenSharing = false;
            // Remove screen share tile
            var screenTile = document.getElementById('tile-' + data.from + '-screen');
            if (screenTile) {
                screenTile.remove();
                self.updateGridLayout();
            }
            // Restore camera tile to normal
            var cameraTile = document.getElementById('tile-' + data.from);
            if (cameraTile) {
                cameraTile.classList.remove('camera-pip');
            }
            self.showNotification(data.username + ' stopped sharing screen');
        }
    });
};

MeetingRoom.prototype.createPeerConnection = function(peerId, createOffer) {
    var self = this;
    
    if (this.peers.has(peerId)) {
        console.log('Peer connection already exists for:', peerId);
        return Promise.resolve(this.peers.get(peerId));
    }
    
    console.log('Creating peer connection for:', peerId);
    
    var pc = new RTCPeerConnection(this.iceServers);
    this.peers.set(peerId, pc);
    this.pendingCandidates.set(peerId, []);
    
    if (this.localStream) {
        this.localStream.getTracks().forEach(function(track) {
            pc.addTrack(track, self.localStream);
        });
    }
    
    pc.onicecandidate = function(event) {
        if (event.candidate) {
            self.socket.emit('ice_candidate', {
                to: peerId,
                candidate: event.candidate
            });
        }
    };
    
    pc.onconnectionstatechange = function() {
        console.log('Connection state with ' + peerId + ':', pc.connectionState);
        if (pc.connectionState === 'connected') {
            console.log('Successfully connected to ' + peerId);
        }
        if (pc.connectionState === 'failed' || pc.connectionState === 'disconnected') {
            self.handlePeerDisconnect(peerId);
        }
    };
    
    pc.oniceconnectionstatechange = function() {
        console.log('ICE connection state with ' + peerId + ':', pc.iceConnectionState);
    };
    
    pc.ontrack = function(event) {
        console.log('=== RECEIVED REMOTE TRACK ===');
        console.log('From peer:', peerId);
        console.log('Track kind:', event.track.kind);
        
        var stream = event.streams[0];
        if (stream) {
            console.log('Stream ID:', stream.id);
            self.remoteStreams.set(peerId, stream);
        } else {
            console.log('No stream in event, creating new stream');
            var existingStream = self.remoteStreams.get(peerId);
            if (!existingStream) {
                existingStream = new MediaStream();
                self.remoteStreams.set(peerId, existingStream);
            }
            existingStream.addTrack(event.track);
            stream = existingStream;
        }
        
        // Debounce video tile updates to avoid interrupting play() calls
        // when both audio and video tracks arrive in quick succession
        if (self.updateTileTimers && self.updateTileTimers.has(peerId)) {
            clearTimeout(self.updateTileTimers.get(peerId));
        }
        
        if (!self.updateTileTimers) {
            self.updateTileTimers = new Map();
        }
        
        var timer = setTimeout(function() {
            var participant = self.participants.get(peerId);
            var username = participant ? participant.username : 'Participant';
            var finalStream = self.remoteStreams.get(peerId);
            if (finalStream) {
                self.updateRemoteVideoTile(peerId, username, finalStream);
            }
            self.updateTileTimers.delete(peerId);
        }, 100); // Small delay to let both tracks arrive
        
        self.updateTileTimers.set(peerId, timer);
    };
    
    if (createOffer) {
        return pc.createOffer({
            offerToReceiveAudio: true,
            offerToReceiveVideo: true
        }).then(function(offer) {
            return pc.setLocalDescription(offer);
        }).then(function() {
            self.socket.emit('offer', {
                to: peerId,
                offer: pc.localDescription
            });
            console.log('Sent offer to:', peerId);
            return pc;
        }).catch(function(error) {
            console.error('Error creating offer:', error);
            return pc;
        });
    }
    
    return Promise.resolve(pc);
};

MeetingRoom.prototype.handleOffer = function(peerId, offer) {
    var self = this;
    var pc = this.peers.get(peerId);
    
    var promise = pc ? Promise.resolve(pc) : this.createPeerConnection(peerId, false);
    
    return promise.then(function(pc) {
        return pc.setRemoteDescription(new RTCSessionDescription(offer));
    }).then(function() {
        pc = self.peers.get(peerId);
        var pending = self.pendingCandidates.get(peerId) || [];
        return Promise.all(pending.map(function(candidate) {
            return pc.addIceCandidate(new RTCIceCandidate(candidate));
        }));
    }).then(function() {
        self.pendingCandidates.set(peerId, []);
        pc = self.peers.get(peerId);
        return pc.createAnswer();
    }).then(function(answer) {
        pc = self.peers.get(peerId);
        return pc.setLocalDescription(answer);
    }).then(function() {
        pc = self.peers.get(peerId);
        self.socket.emit('answer', {
            to: peerId,
            answer: pc.localDescription
        });
        console.log('Sent answer to:', peerId);
    }).catch(function(error) {
        console.error('Error handling offer:', error);
    });
};

MeetingRoom.prototype.handleAnswer = function(peerId, answer) {
    var self = this;
    var pc = this.peers.get(peerId);
    
    if (!pc) return Promise.resolve();
    
    return pc.setRemoteDescription(new RTCSessionDescription(answer)).then(function() {
        var pending = self.pendingCandidates.get(peerId) || [];
        return Promise.all(pending.map(function(candidate) {
            return pc.addIceCandidate(new RTCIceCandidate(candidate));
        }));
    }).then(function() {
        self.pendingCandidates.set(peerId, []);
        console.log('Answer processed for:', peerId);
    }).catch(function(error) {
        console.error('Error handling answer:', error);
    });
};

MeetingRoom.prototype.handleIceCandidate = function(peerId, candidate) {
    var pc = this.peers.get(peerId);
    
    if (pc && pc.remoteDescription) {
        return pc.addIceCandidate(new RTCIceCandidate(candidate)).catch(function(error) {
            console.error('Error adding ICE candidate:', error);
        });
    } else {
        if (!this.pendingCandidates.has(peerId)) {
            this.pendingCandidates.set(peerId, []);
        }
        this.pendingCandidates.get(peerId).push(candidate);
        return Promise.resolve();
    }
};

MeetingRoom.prototype.handlePeerDisconnect = function(peerId) {
    var pc = this.peers.get(peerId);
    if (pc) {
        pc.close();
        this.peers.delete(peerId);
    }
    
    this.remoteStreams.delete(peerId);
    this.participants.delete(peerId);
    this.removeVideoTile(peerId);
    this.updateParticipantCount();
    this.updateParticipantsList();
};

// ==================== VIDEO GRID MANAGEMENT ====================

MeetingRoom.prototype.addVideoTile = function(peerId, username, stream, isLocal) {
    var videoGrid = document.getElementById('videoGrid');
    if (!videoGrid) {
        console.log('Video grid not found!');
        return;
    }
    
    // Strictly check if tile already exists anywhere in the DOM
    var existingTile = document.getElementById('tile-' + peerId);
    if (existingTile) {
        console.log('Tile already exists for:', peerId, '- updating instead');
        var video = existingTile.querySelector('video');
        var avatar = existingTile.querySelector('.avatar-placeholder');
        
        if (stream && stream.getVideoTracks().length > 0) {
            if (video) {
                video.srcObject = stream;
                video.style.display = 'block';
                video.play().catch(function(e) { console.log('Video play error:', e); });
            }
            if (avatar) avatar.style.display = 'none';
        }
        return;
    }
    
    // Create new tile
    console.log('Creating new tile for:', peerId);
    var tile = document.createElement('div');
    tile.id = 'tile-' + peerId;
    tile.className = 'video-tile';
    
    // Make candidate's tile prominent when there are multiple users
    this.applyCandidateMainStyle(tile, peerId);
    
    var videoContainer = document.createElement('div');
    videoContainer.className = 'video-container';
    
    var video = document.createElement('video');
    video.autoplay = true;
    video.playsInline = true;
    video.muted = isLocal;
    
    if (isLocal) {
        video.classList.add('mirror');
    }
    
    if (stream) {
        video.srcObject = stream;
        
        // Wait for loadedmetadata before playing to avoid AbortError
        if (video.readyState >= 2) {
            video.play().catch(function(e) { console.log('Video play error:', e); });
        } else {
            video.addEventListener('loadedmetadata', function onLoaded() {
                video.removeEventListener('loadedmetadata', onLoaded);
                video.play().catch(function(e) { console.log('Video play error after metadata:', e); });
            });
        }
    }
    
    videoContainer.appendChild(video);
    
    var avatar = document.createElement('div');
    avatar.className = 'avatar-placeholder';
    avatar.innerHTML = '<span>' + username.charAt(0).toUpperCase() + '</span>';
    avatar.style.display = (stream && stream.getVideoTracks().length > 0) ? 'none' : 'flex';
    videoContainer.appendChild(avatar);
    
    var nameLabel = document.createElement('div');
    nameLabel.className = 'name-label';
    nameLabel.innerHTML = '<span class="name">' + username + '</span>' +
        '<span class="audio-indicator" id="audio-' + peerId + '">' +
        '<i class="fas fa-microphone"></i></span>';
    
    tile.appendChild(videoContainer);
    tile.appendChild(nameLabel);
    
    // Insert candidate tiles at the beginning, others at the end
    var videoGrid = document.getElementById('videoGrid');
    var isCandidate = false;
    if (peerId === 'local') {
        isCandidate = this.userRole === 'candidate';
    } else {
        var participant = this.participants.get(peerId);
        isCandidate = participant && participant.role === 'candidate';
    }
    
    if (isCandidate && videoGrid.children.length > 0) {
        videoGrid.insertBefore(tile, videoGrid.firstChild);
    } else {
        videoGrid.appendChild(tile);
    }
    
    this.updateGridLayout();
};

MeetingRoom.prototype.addScreenShareTile = function(peerId, username, stream) {
    var videoGrid = document.getElementById('videoGrid');
    if (!videoGrid) {
        console.log('Video grid not found!');
        return;
    }
    
    // Check if tile already exists
    var existingTile = document.getElementById('tile-' + peerId);
    if (existingTile) {
        console.log('Screen share tile already exists');
        return;
    }
    
    // Create new screen share tile
    console.log('Creating screen share tile for:', peerId);
    var tile = document.createElement('div');
    tile.id = 'tile-' + peerId;
    tile.className = 'video-tile screen-share';
    
    var videoContainer = document.createElement('div');
    videoContainer.className = 'video-container';
    
    var video = document.createElement('video');
    video.autoplay = true;
    video.playsInline = true;
    video.muted = true;
    
    if (stream) {
        video.srcObject = stream;
        
        if (video.readyState >= 2) {
            video.play().catch(function(e) { console.log('Screen share play error:', e); });
        } else {
            video.addEventListener('loadedmetadata', function onLoaded() {
                video.removeEventListener('loadedmetadata', onLoaded);
                video.play().catch(function(e) { console.log('Screen share play error after metadata:', e); });
            });
        }
    }
    
    videoContainer.appendChild(video);
    
    var nameLabel = document.createElement('div');
    nameLabel.className = 'name-label';
    nameLabel.innerHTML = '<span class="name">' + username + '</span>' +
        '<span class="audio-indicator">' +
        '<i class="fas fa-desktop"></i></span>';
    
    tile.appendChild(videoContainer);
    tile.appendChild(nameLabel);
    
    // Insert at the beginning of the grid
    videoGrid.insertBefore(tile, videoGrid.firstChild);
    
    this.updateGridLayout();
};

MeetingRoom.prototype.updateRemoteVideoTile = function(peerId, username, stream) {
    console.log('=== UPDATE REMOTE VIDEO TILE ===');
    console.log('Peer ID:', peerId);
    
    var videoGrid = document.getElementById('videoGrid');
    if (!videoGrid) return;
    
    var tile = document.getElementById('tile-' + peerId);
    
    if (tile) {
        var video = tile.querySelector('video');
        var avatar = tile.querySelector('.avatar-placeholder');
        var container = tile.querySelector('.video-container');
        
        if (!video && container) {
            video = document.createElement('video');
            video.autoplay = true;
            video.playsInline = true;
            video.muted = false;
            container.insertBefore(video, container.firstChild);
        }
        
        if (video && stream) {
            // Only update srcObject if it's different to avoid interrupting playback
            if (video.srcObject !== stream) {
                video.srcObject = stream;
                video.style.display = 'block';
                
                // Wait for loadedmetadata before playing to avoid AbortError
                var playPromise = null;
                if (video.readyState >= 2) {
                    // Already has metadata, play immediately
                    playPromise = video.play();
                } else {
                    // Wait for metadata to load
                    video.addEventListener('loadedmetadata', function onLoaded() {
                        video.removeEventListener('loadedmetadata', onLoaded);
                        video.play().catch(function(e) { 
                            console.log('Video play error after metadata:', e); 
                        });
                    });
                }
                
                if (playPromise) {
                    playPromise.catch(function(e) { 
                        console.log('Video play error:', e); 
                    });
                }
            }
        }
        
        if (avatar && stream && stream.getVideoTracks().length > 0) {
            avatar.style.display = 'none';
        }
        
        // Apply candidate-main styling if needed
        this.applyCandidateMainStyle(tile, peerId);
    } else {
        this.addVideoTile(peerId, username, stream, false);
    }
};

MeetingRoom.prototype.removeVideoTile = function(peerId) {
    var tile = document.getElementById('tile-' + peerId);
    if (tile) {
        tile.remove();
        this.updateGridLayout();
    }
};

MeetingRoom.prototype.applyCandidateMainStyle = function(tile, peerId) {
    if (!tile) return;
    
    var videoGrid = document.getElementById('videoGrid');
    if (!videoGrid) return;
    
    // Count total participants (excluding screen shares)
    var participantCount = this.participants.size + 1; // +1 for self
    
    // Only apply if there are 2+ participants
    if (participantCount < 2) {
        tile.classList.remove('candidate-main');
        return;
    }
    
    // Check if this tile is for a candidate
    var isCandidate = false;
    
    if (peerId === 'local') {
        // Check if local user is a candidate
        isCandidate = this.userRole === 'candidate';
    } else {
        // Check if remote user is a candidate
        var participant = this.participants.get(peerId);
        isCandidate = participant && participant.role === 'candidate';
    }
    
    if (isCandidate) {
        tile.classList.add('candidate-main');
        // Move candidate tile to the top
        if (tile.parentElement === videoGrid && videoGrid.firstChild !== tile) {
            videoGrid.insertBefore(tile, videoGrid.firstChild);
        }
        console.log('Applied candidate-main style to:', peerId);
    } else {
        tile.classList.remove('candidate-main');
    }
};

MeetingRoom.prototype.updateAllTilesForCandidateMain = function() {
    var self = this;
    var videoGrid = document.getElementById('videoGrid');
    if (!videoGrid) return;
    
    // Update local tile
    var localTile = document.getElementById('tile-local');
    if (localTile && !localTile.classList.contains('camera-pip')) {
        this.applyCandidateMainStyle(localTile, 'local');
    }
    
    // Update all remote tiles
    this.participants.forEach(function(info, peerId) {
        var tile = document.getElementById('tile-' + peerId);
        if (tile && !tile.classList.contains('camera-pip')) {
            self.applyCandidateMainStyle(tile, peerId);
        }
    });
    
    // Update grid layout to reflect changes
    this.updateGridLayout();
};

MeetingRoom.prototype.updateGridLayout = function() {
    var videoGrid = document.getElementById('videoGrid');
    if (!videoGrid) return;
    
    var count = videoGrid.children.length;
    videoGrid.className = 'video-grid';
    
    // Check if there's a candidate-main tile
    var hasCandidateMain = videoGrid.querySelector('.candidate-main') !== null;
    
    if (hasCandidateMain) {
        videoGrid.classList.add('has-candidate-main');
    } else if (count === 1) {
        videoGrid.classList.add('grid-1');
    } else if (count === 2) {
        videoGrid.classList.add('grid-2');
    } else if (count === 3) {
        videoGrid.classList.add('grid-3');
    } else if (count === 4) {
        videoGrid.classList.add('grid-4');
    } else if (count <= 6) {
        videoGrid.classList.add('grid-6');
    } else {
        videoGrid.classList.add('grid-many');
    }
};

// ==================== CONTROLS ====================

MeetingRoom.prototype.toggleAudio = function() {
    if (this.localStream) {
        var audioTrack = this.localStream.getAudioTracks()[0];
        if (audioTrack) {
            audioTrack.enabled = !audioTrack.enabled;
            this.isAudioEnabled = audioTrack.enabled;
            
            var btn = document.getElementById('btnMic');
            if (btn) {
                btn.innerHTML = this.isAudioEnabled 
                    ? '<i class="fas fa-microphone"></i>' 
                    : '<i class="fas fa-microphone-slash"></i>';
                if (this.isAudioEnabled) {
                    btn.classList.remove('btn-danger');
                } else {
                    btn.classList.add('btn-danger');
                }
            }
            
            var indicator = document.getElementById('audio-local');
            if (indicator) {
                indicator.innerHTML = this.isAudioEnabled 
                    ? '<i class="fas fa-microphone"></i>'
                    : '<i class="fas fa-microphone-slash" style="color: #ea4335;"></i>';
            }
        }
    }
};

MeetingRoom.prototype.toggleVideo = function() {
    var self = this;
    if (this.localStream) {
        var videoTrack = this.localStream.getVideoTracks()[0];
        if (videoTrack) {
            videoTrack.enabled = !videoTrack.enabled;
            this.isVideoEnabled = videoTrack.enabled;
            
            var btn = document.getElementById('btnCamera');
            if (btn) {
                btn.innerHTML = this.isVideoEnabled 
                    ? '<i class="fas fa-video"></i>' 
                    : '<i class="fas fa-video-slash"></i>';
                if (this.isVideoEnabled) {
                    btn.classList.remove('btn-danger');
                } else {
                    btn.classList.add('btn-danger');
                }
            }
            
            var tile = document.getElementById('tile-local');
            if (tile) {
                var video = tile.querySelector('video');
                var avatar = tile.querySelector('.avatar-placeholder');
                
                if (this.isVideoEnabled) {
                    if (video) video.style.display = 'block';
                    if (avatar) avatar.style.display = 'none';
                } else {
                    if (video) video.style.display = 'none';
                    if (!avatar) {
                        var newAvatar = document.createElement('div');
                        newAvatar.className = 'avatar-placeholder';
                        newAvatar.innerHTML = '<span>' + self.username.charAt(0).toUpperCase() + '</span>';
                        tile.querySelector('.video-container').appendChild(newAvatar);
                    } else {
                        avatar.style.display = 'flex';
                    }
                }
            }
        }
    }
};

MeetingRoom.prototype.toggleScreenShare = function() {
    var self = this;
    
    if (!this.isScreenSharing) {
        navigator.mediaDevices.getDisplayMedia({
            video: { cursor: 'always' },
            audio: false
        }).then(function(stream) {
            self.screenStream = stream;
            var screenTrack = stream.getVideoTracks()[0];
            
            // Replace video track in peer connections with screen track
            self.peers.forEach(function(pc) {
                var sender = pc.getSenders().find(function(s) { 
                    return s.track && s.track.kind === 'video'; 
                });
                if (sender) {
                    sender.replaceTrack(screenTrack);
                }
            });
            
            // Create a new tile for screen share
            var screenTile = document.getElementById('tile-local-screen');
            if (screenTile) {
                screenTile.remove();
            }
            
            self.addScreenShareTile('local-screen', self.username + "'s Screen", stream);
            
            // Convert local camera tile to picture-in-picture
            var localTile = document.getElementById('tile-local');
            if (localTile) {
                // Remove candidate-main class during screen sharing
                localTile.classList.remove('candidate-main');
                localTile.classList.add('camera-pip');
                var video = localTile.querySelector('video');
                if (video) {
                    video.srcObject = self.localStream;
                    video.classList.add('mirror');
                }
                // Move to video area container for proper positioning
                var videoArea = document.getElementById('videoArea');
                if (videoArea && localTile.parentElement !== videoArea) {
                    videoArea.appendChild(localTile);
                }
            }
            
            self.isScreenSharing = true;
            
            // Notify other participants
            self.socket.emit('screen_share_started', {
                room: self.roomId
            });
            
            var btn = document.getElementById('btnScreenShare');
            if (btn) btn.classList.add('active');
            
            self.showNotification('Screen sharing started');
            
            screenTrack.onended = function() { self.stopScreenShare(); };
            
        }).catch(function(error) {
            console.error('Error starting screen share:', error);
        });
    } else {
        this.stopScreenShare();
    }
};

MeetingRoom.prototype.stopScreenShare = function() {
    var self = this;
    
    if (this.screenStream) {
        this.screenStream.getTracks().forEach(function(track) { track.stop(); });
        this.screenStream = null;
    }
    
    // Remove screen share tile
    var screenTile = document.getElementById('tile-local-screen');
    if (screenTile) {
        screenTile.remove();
        this.updateGridLayout();
    }
    
    // Restore camera video track to peers
    if (this.localStream) {
        var videoTrack = this.localStream.getVideoTracks()[0];
        if (videoTrack) {
            this.peers.forEach(function(pc) {
                var sender = pc.getSenders().find(function(s) { 
                    return s.track && s.track.kind === 'video'; 
                });
                if (sender) {
                    sender.replaceTrack(videoTrack);
                }
            });
        }
        
        // Restore local camera tile to normal position
        var localTile = document.getElementById('tile-local');
        if (localTile) {
            localTile.classList.remove('camera-pip');
            var video = localTile.querySelector('video');
            if (video) {
                video.srcObject = this.localStream;
                video.classList.add('mirror');
            }
            // Move back to video grid
            var videoGrid = document.getElementById('videoGrid');
            if (videoGrid && localTile.parentElement !== videoGrid) {
                videoGrid.insertBefore(localTile, videoGrid.firstChild);
            }
            // Restore candidate-main styling if applicable
            this.applyCandidateMainStyle(localTile, 'local');
        }
    }
    
    this.isScreenSharing = false;
    
    // Notify other participants
    this.socket.emit('screen_share_stopped', {
        room: this.roomId
    });
    
    var btn = document.getElementById('btnScreenShare');
    if (btn) btn.classList.remove('active');
    
    this.showNotification('Screen sharing stopped');
};

// ==================== CHAT ====================

MeetingRoom.prototype.toggleChat = function() {
    var sidebar = document.getElementById('sidebar');
    var chatPanel = document.getElementById('chatPanel');
    var participantsPanel = document.getElementById('participantsPanel');
    
    if (this.isChatOpen) {
        sidebar.classList.remove('open');
        this.isChatOpen = false;
    } else {
        sidebar.classList.add('open');
        chatPanel.style.display = 'flex';
        participantsPanel.style.display = 'none';
        this.isChatOpen = true;
        this.isParticipantsOpen = false;
        this.unreadCount = 0;
        this.updateUnreadBadge();
        
        var input = document.getElementById('chatInput');
        if (input) input.focus();
    }
};

MeetingRoom.prototype.toggleParticipants = function() {
    var sidebar = document.getElementById('sidebar');
    var chatPanel = document.getElementById('chatPanel');
    var participantsPanel = document.getElementById('participantsPanel');
    
    if (this.isParticipantsOpen) {
        sidebar.classList.remove('open');
        this.isParticipantsOpen = false;
    } else {
        sidebar.classList.add('open');
        chatPanel.style.display = 'none';
        participantsPanel.style.display = 'flex';
        this.isParticipantsOpen = true;
        this.isChatOpen = false;
    }
};

MeetingRoom.prototype.closeSidebar = function() {
    var sidebar = document.getElementById('sidebar');
    sidebar.classList.remove('open');
    this.isChatOpen = false;
    this.isParticipantsOpen = false;
};

MeetingRoom.prototype.sendMessage = function() {
    var input = document.getElementById('chatInput');
    if (!input) return;
    
    var message = input.value.trim();
    if (!message) return;
    
    this.socket.emit('chat_message', {
        room: this.roomId,
        message: message
    });
    
    this.addChatMessage(this.username, message, new Date().toISOString(), true);
    input.value = '';
};

MeetingRoom.prototype.addChatMessage = function(username, message, timestamp, isLocal) {
    var container = document.getElementById('chatMessages');
    if (!container) return;
    
    var time = new Date(timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    
    var msgDiv = document.createElement('div');
    msgDiv.className = 'chat-message ' + (isLocal ? 'sent' : 'received');
    msgDiv.innerHTML = '<div class="message-header">' +
        '<span class="sender">' + username + '</span>' +
        '<span class="time">' + time + '</span></div>' +
        '<div class="message-body">' + this.escapeHtml(message) + '</div>';
    
    container.appendChild(msgDiv);
    container.scrollTop = container.scrollHeight;
    
    if (!isLocal && !this.isChatOpen) {
        this.unreadCount++;
        this.updateUnreadBadge();
    }
    
    this.messages.push({ username: username, message: message, timestamp: timestamp, isLocal: isLocal });
};

MeetingRoom.prototype.updateUnreadBadge = function() {
    var badge = document.getElementById('chatBadge');
    if (badge) {
        if (this.unreadCount > 0) {
            badge.textContent = this.unreadCount > 99 ? '99+' : this.unreadCount;
            badge.style.display = 'flex';
        } else {
            badge.style.display = 'none';
        }
    }
};

MeetingRoom.prototype.escapeHtml = function(text) {
    var div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
};

// ==================== PARTICIPANTS ====================

MeetingRoom.prototype.updateParticipantCount = function() {
    var count = this.participants.size + 1;
    var countEl = document.getElementById('participantCount');
    if (countEl) {
        countEl.textContent = count;
    }
};

MeetingRoom.prototype.updateParticipantsList = function() {
    var self = this;
    var container = document.getElementById('participantsList');
    if (!container) return;
    
    container.innerHTML = '';
    container.innerHTML += this.createParticipantItem(this.username + ' (You)', this.userRole, true);
    
    this.participants.forEach(function(info) {
        container.innerHTML += self.createParticipantItem(info.username, info.role, false);
    });
};

MeetingRoom.prototype.createParticipantItem = function(name, role, isSelf) {
    var roleLabel = role === 'interviewer' ? 'Interviewer' : 'Candidate';
    var roleClass = role === 'interviewer' ? 'role-interviewer' : 'role-candidate';
    
    return '<div class="participant-item ' + (isSelf ? 'self' : '') + '">' +
        '<div class="participant-avatar">' + name.charAt(0).toUpperCase() + '</div>' +
        '<div class="participant-info">' +
        '<div class="participant-name">' + name + '</div>' +
        '<div class="participant-role ' + roleClass + '">' + roleLabel + '</div></div>' +
        '<div class="participant-actions"><i class="fas fa-microphone"></i></div></div>';
};

// ==================== MEETING CONTROLS ====================

MeetingRoom.prototype.leaveMeeting = function() {
    var self = this;
    
    if (!confirm('Are you sure you want to leave this meeting?')) return;
    
    if (this.localStream) {
        this.localStream.getTracks().forEach(function(track) { track.stop(); });
    }
    if (this.screenStream) {
        this.screenStream.getTracks().forEach(function(track) { track.stop(); });
    }
    
    this.peers.forEach(function(pc) { pc.close(); });
    this.peers.clear();
    
    if (this.socket) {
        this.socket.emit('leave_interview', { room: this.roomId });
        this.socket.disconnect();
    }
    
    if (this.userRole === 'interviewer') {
        window.location.href = '/interview/' + this.roomCode + '/feedback';
    } else {
        window.location.href = '/candidate/interviews';
    }
};

// ==================== UI HELPERS ====================

MeetingRoom.prototype.setupUIListeners = function() {
    var self = this;
    
    var btnMic = document.getElementById('btnMic');
    if (btnMic) btnMic.addEventListener('click', function() { self.toggleAudio(); });
    
    var btnCamera = document.getElementById('btnCamera');
    if (btnCamera) btnCamera.addEventListener('click', function() { self.toggleVideo(); });
    
    var btnScreenShare = document.getElementById('btnScreenShare');
    if (btnScreenShare) btnScreenShare.addEventListener('click', function() { self.toggleScreenShare(); });
    
    var btnChat = document.getElementById('btnChat');
    if (btnChat) btnChat.addEventListener('click', function() { self.toggleChat(); });
    
    var btnParticipants = document.getElementById('btnParticipants');
    if (btnParticipants) btnParticipants.addEventListener('click', function() { self.toggleParticipants(); });
    
    var btnLeave = document.getElementById('btnLeave');
    if (btnLeave) btnLeave.addEventListener('click', function() { self.leaveMeeting(); });
    
    var btnCloseSidebar = document.getElementById('btnCloseSidebar');
    if (btnCloseSidebar) btnCloseSidebar.addEventListener('click', function() { self.closeSidebar(); });
    
    var chatInput = document.getElementById('chatInput');
    if (chatInput) {
        chatInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                self.sendMessage();
            }
        });
    }
    
    var btnSendMessage = document.getElementById('btnSendMessage');
    if (btnSendMessage) btnSendMessage.addEventListener('click', function() { self.sendMessage(); });
};

MeetingRoom.prototype.showNotification = function(message) {
    var container = document.getElementById('notifications');
    if (!container) return;
    
    var notification = document.createElement('div');
    notification.className = 'notification';
    notification.textContent = message;
    
    container.appendChild(notification);
    
    setTimeout(function() {
        notification.classList.add('fade-out');
        setTimeout(function() { notification.remove(); }, 300);
    }, 3000);
};

MeetingRoom.prototype.showError = function(message) {
    alert(message);
};

// ==================== INITIALIZATION ====================

window.MeetingRoom = MeetingRoom;

window.initializeMeeting = function(config) {
    // Always clean up and create fresh
    if (window.meetingRoom) {
        console.log('Cleaning up existing meeting before reinitializing...');
        try {
            if (window.meetingRoom.localStream) {
                window.meetingRoom.localStream.getTracks().forEach(function(t) { t.stop(); });
            }
            if (window.meetingRoom.socket) {
                window.meetingRoom.socket.disconnect();
            }
            if (window.meetingRoom.peers) {
                window.meetingRoom.peers.forEach(function(pc) { pc.close(); });
            }
        } catch(e) { console.log('Cleanup error:', e); }
    }
    
    // Clear video grid
    var videoGrid = document.getElementById('videoGrid');
    if (videoGrid) {
        videoGrid.innerHTML = '';
    }
    
    console.log('Initializing meeting with config:', config);
    window.meetingRoom = new MeetingRoom(config);
    return window.meetingRoom;
};

// Auto-initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function() {
        if (window.meetingConfig) {
            window.initializeMeeting(window.meetingConfig);
        }
    });
} else {
    // DOM already loaded
    if (window.meetingConfig) {
        window.initializeMeeting(window.meetingConfig);
    }
}

})();
