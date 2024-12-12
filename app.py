# from flask import Flask, render_template, request, jsonify, Response, make_response, send_from_directory
# from flask_cors import CORS
# import azure.cognitiveservices.speech as speechsdk
# from azure.cognitiveservices.speech import SpeechConfig
# import requests
# import queue
# import logging
# import json
# import pyaudio
# import asyncio
# import uuid
# import signal
# import os
# import tempfile
# import time
# from datetime import datetime
# from cachetools import TTLCache
# from collections import deque
# import sys
# from concurrent.futures import ThreadPoolExecutor
# from dotenv import load_dotenv
# from werkzeug.serving import is_running_from_reloader
# import logging

# executor = ThreadPoolExecutor(max_workers=10)

# load_dotenv()
# # Configure logging
# log_directory = "logs"
# if not os.path.exists(log_directory):
#     os.makedirs(log_directory)

# # Create handlers for both file and console logging
# current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
# file_handler = logging.FileHandler(f'{log_directory}/app_{current_time}.log')
# console_handler = logging.StreamHandler(sys.stdout)

# # Create formatters and add it to handlers
# log_format = logging.Formatter('%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d - %(message)s')
# file_handler.setFormatter(log_format)
# console_handler.setFormatter(log_format)

# # Get the logger and add handlers
# logger = logging.getLogger(__name__)
# logger.setLevel(logging.DEBUG)
# logger.addHandler(file_handler)
# logger.addHandler(console_handler)
        
# app = Flask(__name__)
# CORS(app, resources={r"/*": {"origins": "*"}})

# # Microsoft Translator API configuration
# speech_key= os.getenv('AZURE_SPEECH_KEY')
# service_region= os.getenv('AZURE_SPEECH_REGION')
# TRANSLATOR_KEY = os.getenv('AZURE_TRANSLATOR_KEY')
# TRANSLATOR_ENDPOINT= os.getenv('AZURE_TRANSLATOR_ENDPOINT')
# TRANSLATOR_LOCATION=  os.getenv('AZURE_TRANSLATOR_LOCATION')

# # Global variables for live streaming
# is_streaming = False
# transcription_queue = queue.Queue()
# audio_queue = queue.Queue()
# is_recording = False
# cleanup_done = False
# recording_file = None
# RECORDINGS_DIR = "recordings"



# # Initialize translation cache with TTLCache
# translation_cache = TTLCache(maxsize=10000, ttl=360000)  # Cache translations for 1 hour

# # Rate limiting configuration
# translation_rate_limit = {
#     'requests': deque(maxlen=5000),  
#     'limit': 5000,  # Number of requests allowed
#     'window': 60  # Time window in seconds
# }

# # Dictionary to manage connected clients
# connected_clients = {}

# def shutdown_handler(signum, frame):
#     global is_streaming
#     logger.info("Shutting down server...")
#     is_streaming = False
#     executor.shutdown(wait=True)
#     logger.info("Server shutdown complete.")

# signal.signal(signal.SIGINT, shutdown_handler)
# signal.signal(signal.SIGTERM, shutdown_handler)

# # Ensure the recordings directory exists
# if not os.path.exists(RECORDINGS_DIR):
#     os.makedirs(RECORDINGS_DIR)
#     logger.info(f"Created recordings directory: {RECORDINGS_DIR}")

# # Audio settings
# CHUNK = 1024
# FORMAT = pyaudio.paInt16
# CHANNELS = 1
# RATE = 16000

# def cleanup():
#     global is_streaming, cleanup_done
#     if not cleanup_done:
#         logger.info("Cleaning up resources...")
#         is_streaming = False
#         executor.shutdown(wait=False)
#         cleanup_done = True
#         logger.info("Cleanup completed")

# def signal_handler(signum, frame):
#     cleanup()
#     sys.exit(0)

# signal.signal(signal.SIGINT, signal_handler)
# signal.signal(signal.SIGTERM, signal_handler)

# class RequestIdMiddleware:
#     def __init__(self, app):
#         self.app = app

#     def __call__(self, environ, start_response):
#         request_id = str(uuid.uuid4())
#         environ['REQUEST_ID'] = request_id
#         logger.debug(f'New request started with ID: {request_id}')
#         return self.app(environ, start_response)

# app.wsgi_app = RequestIdMiddleware(app.wsgi_app)

# async def translate_with_microsoft(text, target_language):
#     logger.info(f"Starting translation request for language: {target_language}")
#     logger.debug(f"Text to translate: {text}")
    
#     try:
#         # Check cache first
#         cache_key = f"{text}:{target_language}"
#         if cache_key in translation_cache:
#             logger.debug("Translation found in cache")
#             return translation_cache[cache_key]

#         # Rate limiting check
#         current_time = time.time()
#         translation_rate_limit['requests'].append(current_time)
        
#         # Remove old requests outside the time window
#         while translation_rate_limit['requests'] and \
#               translation_rate_limit['requests'][0] < current_time - translation_rate_limit['window']:
#             translation_rate_limit['requests'].popleft()
        
#         # Check if we've exceeded the rate limit
#         if len(translation_rate_limit['requests']) > translation_rate_limit['limit']:
#             wait_time = translation_rate_limit['requests'][0] + translation_rate_limit['window'] - current_time
#             if wait_time > 0:
#                 logger.warning(f"Rate limit exceeded. Waiting {wait_time:.2f} seconds")
#                 await asyncio.sleep(wait_time)

#         # Construct the request
#         endpoint = f'{TRANSLATOR_ENDPOINT}/translate'
#         params = {
#             'api-version': '3.0',
#             'to': target_language
#         }
#         headers = {
#             'Ocp-Apim-Subscription-Key': TRANSLATOR_KEY,
#             'Ocp-Apim-Subscription-Region': TRANSLATOR_LOCATION,
#             'Content-type': 'application/json'
#         }
#         body = [{
#             'text': text
#         }]

#         # Make the request
#         response = requests.post(endpoint, params=params, headers=headers, json=body)
#         response.raise_for_status()
        
#         translation_result = response.json()
#         translated_text = translation_result[0]['translations'][0]['text']
        
#         # Cache the result
#         translation_cache[cache_key] = translated_text
#         logger.info(f"Translation successful for {target_language}")
#         logger.debug(f"Translated text: {translated_text}")
        
#         return translated_text
#     except Exception as e:
#         logger.error(f"Translation error: {str(e)}", exc_info=True)
#         if isinstance(e, requests.exceptions.HTTPError) and e.response.status_code == 429:
#             # Handle rate limit exceeded specifically
#             retry_after = int(e.response.headers.get('Retry-After', 60))
#             logger.warning(f"Rate limit exceeded. Retry after {retry_after} seconds")
#             await asyncio.sleep(retry_after)
#             # Retry the translation once after waiting
#             return await translate_with_microsoft(text, target_language)
#         return text

# @app.route('/')
# def home():
#     logger.info("Home page requested")
#     return render_template('index.html')

# @app.errorhandler(500)
# def internal_error(error):
#     logger.error(f"500 error: {str(error)}", exc_info=True)
#     return jsonify({
#         "error": "Internal Server Error",
#         "message": "An internal server error occurred."
#     }), 500

# @app.route('/favicon.ico')
# def favicon():
#     return send_from_directory(
#         os.path.join(app.root_path, 'static'),
#         'favicon.ico',
#         mimetype='image/vnd.microsoft.icon'
#     )

# # Add a 404 error handler
# @app.errorhandler(404)
# def not_found_error(error):
#     logger.warning(f"404 error: {request.url}")
#     if request.path == '/favicon.ico':
#         return '', 204  # Return empty response with 204 status if favicon is not found
#     return jsonify({
#         "error": "Not Found",
#         "message": "The requested URL was not found on the server."
#     }), 404

# @app.route('/synthesize_speech', methods=['POST'])
# def synthesize_speech():
#     try:
#         data = request.get_json()
#         text = data.get('text')
#         language = data.get('language')

#         if not text:
#             return jsonify({'error': 'No text provided'}), 400

#         # Configure speech service
#         speech_config = SpeechConfig(
#             subscription=speech_key,
#             region=service_region
#         )

#         # Set voice based on language
#         if language == 'pt':
#             speech_config.speech_synthesis_voice_name = "pt-BR-AntonioNeural"
#         elif language == 'es':
#             speech_config.speech_synthesis_voice_name = "es-ES-AlvaroNeural"
#         else:
#             return jsonify({'error': 'Unsupported language'}), 400

#         logger.info(f"Using voice for language {language}: {speech_config.speech_synthesis_voice_name}")

#         # Create a temporary file to store the audio
#         temp_file = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
#         temp_filename = temp_file.name
#         temp_file.close()

#         try:
#             # Configure audio output to file
#             audio_config = speechsdk.audio.AudioOutputConfig(
#                 filename=temp_filename
#             )

#             # Create synthesizer
#             synthesizer = speechsdk.SpeechSynthesizer(
#                 speech_config=speech_config,
#                 audio_config=audio_config
#             )

#             # Synthesize text
#             result = synthesizer.speak_text_async(text).get()

#             if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
#                 # Read the audio file
#                 with open(temp_filename, 'rb') as audio_file:
#                     audio_data = audio_file.read()

#                 # Create response
#                 response = make_response(audio_data)
#                 response.headers['Content-Type'] = 'audio/wav'
#                 response.headers['Content-Disposition'] = 'attachment; filename=speech.wav'
                
#                 logger.info("Speech synthesis completed successfully")
#                 return response
#             else:
#                 error_details = result.cancellation_details
#                 logger.error(f"Speech synthesis failed: {error_details.reason}")
#                 return jsonify({
#                     'error': 'Speech synthesis failed',
#                     'details': error_details.error_details
#                 }), 500

#         finally:
#             # Clean up the temporary file
#             try:
#                 os.unlink(temp_filename)
#             except Exception as e:
#                 logger.warning(f"Error removing temporary file: {e}")

#     except Exception as e:
#         logger.error(f"Speech synthesis error: {str(e)}", exc_info=True)
#         return jsonify({'error': str(e)}), 500


# @app.route('/start_recording', methods=['POST'])
# def start_recording():
#     global is_recording, recording_file
#     logger.info("Recording start requested")
    
#     if not is_recording:
#         filename = f"transcription_{uuid.uuid4()}.txt"
#         file_path = os.path.join(RECORDINGS_DIR, filename)
#         recording_file = open(file_path, 'w', encoding='utf-8')
#         is_recording = True
#         logger.info(f"Recording started: {file_path}")
#         return jsonify({"status": "recording_started", "file": filename}), 200
#     else:
#         logger.warning("Attempted to start recording while already recording")
#         return jsonify({"status": "already_recording"}), 400

# @app.route('/stop_recording', methods=['POST'])
# def stop_recording():
#     global is_recording, recording_file
#     logger.info("Recording stop requested")
    
#     if is_recording and recording_file:
#         recording_file.close()
#         logger.info("Recording stopped and file closed")
#         is_recording = False
#         recording_file = None
#         return jsonify({"status": "recording_stopped"}), 200
#     else:
#         logger.warning("Attempted to stop recording while not recording")
#         return jsonify({"status": "not_recording"}), 400

# @app.route('/translate', methods=['POST'])
# async def translate():
#     logger.info("Translation endpoint called")
#     try:
#         data = request.get_json()
#         logger.debug(f"Translation request data: {data}")

#         text = data.get('text', '')
#         target_language = data.get('targetLanguage', '')
#         client_id = data.get('clientId')

#         if not text or not target_language or not client_id:
#             logger.warning("Missing required parameters for translation")
#             return jsonify({'error': 'Missing required parameters'}), 400

#         translated_text = await translate_with_microsoft(text, target_language)

#         # Ensure the client is registered
#         if client_id not in connected_clients:
#             logger.warning(f"Client ID {client_id} not connected for translation")
#             return jsonify({'error': 'Client not connected for translation'}), 400

#         translation_queue = connected_clients[client_id]['translation_queue']
#         translation_queue.put(translated_text)
#         logger.debug(f"Translation added to queue for client: {client_id}")

#         return jsonify({'translatedText': translated_text})
#     except Exception as e:
#         logger.error(f"Translation endpoint error: {str(e)}", exc_info=True)
#         return jsonify({'error': str(e)}), 500

# @app.route('/go_live')
# def go_live():
#     logger.info("Go live page requested")
#     return render_template('go_live1.html')

# @app.route('/join_live')
# def join_live():
#     logger.info("Join live page requested")
#     return render_template('join_live.html')

# @app.route('/start_stream', methods=['POST'])
# def start_stream():
#     global is_streaming
#     request_type = request.args.get('type', '')
#     logger.info(f"Stream start requested. Type: {request_type}")
    
#     if request_type == 'broadcaster':
#         if not is_streaming:
#             is_streaming = True
#             executor.submit(stream_audio)  
#             logger.info("Broadcasting started")
#             return jsonify({"status": "started"})
#         else:
#             logger.warning("Attempted to start stream while already streaming")
#     else:
#         logger.info("Listener connected")
#     return jsonify({"status": "connected"})

# @app.route('/stop_stream', methods=['POST'])
# def stop_stream():
#     global is_streaming
#     logger.info("Stream stop requested")
#     is_streaming = False
#     return jsonify({"status": "stopped"})

# @app.route('/translate_realtime', methods=['POST'])
# async def translate_realtime():
#     logger.info("Real-time translation endpoint called")
#     try:
#         data = request.get_json()
#         logger.debug(f"Real-time translation request data: {data}")

#         text = data.get('text', '').strip()
#         target_language = data.get('targetLanguage', '')
#         client_id = data.get('clientId')
#         is_final = data.get('isFinal', False)

#         # Skip empty text
#         if not text:
#             return jsonify({'success': True})

#         if not target_language or not client_id:
#             logger.warning("Missing required parameters for translation")
#             return jsonify({'error': 'Missing required parameters'}), 400

#         # Map language codes for Microsoft Translator
#         language_map = {
#             'es': 'es',
#             'en': 'en',
#             'pt': 'pt'
#         }

#         target_lang = language_map.get(target_language)
#         if not target_lang:
#             logger.warning(f"Invalid target language: {target_language}")
#             return jsonify({'error': 'Invalid target language'}), 400

#         try:
#             # Construct the request for Microsoft Translator
#             endpoint = f'{TRANSLATOR_ENDPOINT}/translate'
#             params = {
#                 'api-version': '3.0',
#                 'to': target_lang
#             }
#             headers = {
#                 'Ocp-Apim-Subscription-Key': TRANSLATOR_KEY,
#                 'Ocp-Apim-Subscription-Region': TRANSLATOR_LOCATION,
#                 'Content-type': 'application/json'
#             }
#             body = [{
#                 'text': text
#             }]

#             # Make the translation request
#             response = requests.post(endpoint, params=params, headers=headers, json=body)
#             response.raise_for_status()
            
#             translation_result = response.json()
#             translated_text = translation_result[0]['translations'][0]['text']
            
#             # Ensure the client is registered
#             if client_id not in connected_clients:
#                 connected_clients[client_id] = {
#                     'target_language': target_language,
#                     'translation_queue': queue.Queue()
#                 }

#             translation_queue = connected_clients[client_id]['translation_queue']
#             message = {
#                 'type': 'final' if is_final else 'partial',
#                 'translation': translated_text
#             }
#             translation_queue.put(message)
#             logger.debug(f"Translation successful: {translated_text}")

#             return jsonify({'success': True})

#         except requests.exceptions.RequestException as e:
#             logger.error(f"Translation request error: {str(e)}")
#             return jsonify({'error': f'Translation service error: {str(e)}'}), 500

#     except Exception as e:
#         logger.error(f"Translation endpoint error: {str(e)}", exc_info=True)
#         return jsonify({'error': str(e)}), 500


# @app.route('/stream_transcription')
# def stream_transcription():
#     logger.info("New transcription stream connection")
#     def generate():
#         while True:
#             try:
#                 item = transcription_queue.get(timeout=1)
#                 transcription = item['text']
#                 is_final = item['is_final']
#                 logger.debug(f"Sending transcription: {transcription}, is_final: {is_final}")
#                 if is_recording and recording_file and is_final:
#                     recording_file.write(transcription + '\n')
#                 yield f"data: {json.dumps({'transcription': transcription, 'is_final': is_final})}\n\n"
#             except queue.Empty:
#                 yield f"data: {json.dumps({'keepalive': True})}\n\n"

#     response = Response(generate(), mimetype='text/event-stream')
#     response.headers.update({
#         'Cache-Control': 'no-cache',
#         'X-Accel-Buffering': 'no',
#         'Access-Control-Allow-Origin': '*',
#         'Connection': 'keep-alive'
#     })
#     return response

# @app.route('/stream_translation/<string:lang>')
# def stream_translation(lang):
#     client_id = request.args.get('client_id')
#     logger.info(f"New translation stream connection for client: {client_id}, language: {lang}")

#     # Validate language code
#     valid_languages = ['en', 'es', 'pt']
#     if lang not in valid_languages:
#         logger.warning(f"Invalid language code: {lang}")
#         return jsonify({'error': 'Invalid language code'}), 400 

#     def generate():
#         # Create a new queue and store client info if not already present
#         if client_id not in connected_clients:
#             connected_clients[client_id] = {
#                 'target_language': lang,
#                 'translation_queue': queue.Queue()
#             }
#             logger.debug(f"Created new translation queue for client: {client_id}")

#         translation_queue = connected_clients[client_id]['translation_queue']

#         while True:
#             try:
#                 message = translation_queue.get(timeout=1)
#                 yield f"data: {json.dumps(message)}\n\n"
#             except queue.Empty:
#                 yield f"data: {json.dumps({'keepalive': True})}\n\n"
#             except GeneratorExit:
#                 logger.info(f"Client {client_id} disconnected from translation stream")
#                 if client_id in connected_clients:
#                     del connected_clients[client_id]
#                     logger.debug(f"Cleaned up translation queue for client {client_id}")
#                 break

#     response = Response(generate(), mimetype='text/event-stream')
#     response.headers.update({
#         'Cache-Control': 'no-cache',
#         'X-Accel-Buffering': 'no',
#         'Access-Control-Allow-Origin': '*',
#         'Connection': 'keep-alive'
#     })
#     return response
    
# # def stream_audio():
# #     logger.info("Initializing audio streaming")
# #     try:
# #         speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=service_region)
# #         speech_config.speech_recognition_language = "en-US"
# #         audio_config = speechsdk.audio.AudioConfig(use_default_microphone=True)
        
# #         speech_recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)
        
# #         async def handle_translation(text):
# #             for client_id, client_info in connected_clients.items():
# #                 target_language = client_info['target_language']
# #                 translation_queue = client_info['translation_queue']
# #                 try:
# #                     translated_text = await translate_with_microsoft(text, target_language)
# #                     message = {
# #                         'type': 'final',
# #                         'translation': translated_text
# #                     }
# #                     translation_queue.put(message)
# #                     logger.debug(f"Translation handled for client {client_id} in language {target_language}: {translated_text}")
# #                 except Exception as e:
# #                     logger.error(f"Translation error for client {client_id}: {str(e)}", exc_info=True)

# #         def recognized_cb(evt):
# #             text = evt.result.text
# #             logger.info(f"Speech recognized: {text}")
# #             transcription_queue.put({'text': text, 'is_final': True})
# #             asyncio.run(handle_translation(text))

# #         def recognizing_cb(evt):
# #             text = evt.result.text
# #             logger.debug(f"Speech recognizing: {text}")
# #             transcription_queue.put({'text': text, 'is_final': False})

        
# #         speech_recognizer.recognized.connect(recognized_cb)
# #         speech_recognizer.recognizing.connect(recognizing_cb)


# #         logger.info("Starting continuous recognition")
# #         speech_recognizer.start_continuous_recognition()
        
# #         p = pyaudio.PyAudio()
# #         stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)
# #         logger.info("Audio stream opened")
        
# #         global is_streaming
# #         while is_streaming:
# #             try:
# #                 data = stream.read(CHUNK)
# #                 audio_queue.put(data)
# #             except Exception as e:
# #                 logger.error(f"Error reading audio stream: {str(e)}", exc_info=True)
# #                 break
        
# #         logger.info("Cleaning up audio stream")
# #         stream.stop_stream()
# #         stream.close()
# #         p.terminate()
# #         speech_recognizer.stop_continuous_recognition()
# #         logger.info("Audio streaming stopped")
# #     except Exception as e:
# #         logger.error(f"Error in stream_audio: {str(e)}", exc_info=True)

# def stream_audio():
#     logger.info("Initializing audio streaming")
#     speech_recognizer = None
#     audio_stream = None
#     pyaudio_instance = None
    
#     try:
#         max_retries = 3
#         retry_count = 0
        
#         while retry_count < max_retries:
#             try:
#                 speech_config = speechsdk.SpeechConfig(
#                     subscription=speech_key, 
#                     region=service_region
#                 )
#                 speech_config.speech_recognition_language = "en-US"
                
#                 # Set up basic audio configuration
#                 audio_config = speechsdk.audio.AudioConfig(use_default_microphone=True)
#                 speech_recognizer = speechsdk.SpeechRecognizer(
#                     speech_config=speech_config, 
#                     audio_config=audio_config
#                 )
                
#                 break
#             except Exception as e:
#                 retry_count += 1
#                 logger.error(f"Speech service initialization attempt {retry_count} failed: {str(e)}")
#                 if retry_count >= max_retries:
#                     raise
#                 time.sleep(2 ** retry_count)
        
#         async def handle_translation(text):
#             for client_id, client_info in connected_clients.items():
#                 try:
#                     target_language = client_info['target_language']
#                     translation_queue = client_info['translation_queue']
                    
#                     translated_text = await translate_with_microsoft(text, target_language)
#                     message = {
#                         'type': 'final',
#                         'translation': translated_text
#                     }
#                     translation_queue.put(message)
#                     logger.debug(f"Translation handled for client {client_id}: {translated_text}")
#                 except Exception as e:
#                     logger.error(f"Translation error for client {client_id}: {str(e)}")
        
#         def handle_session_started(evt):
#             logger.info("Speech session started successfully")
            
#         def handle_session_stopped(evt):
#             logger.info("Speech session stopped")
            
#         def handle_canceled(evt):
#             cancellation_details = evt.result.cancellation_details
#             logger.error(f"Speech recognition canceled: {cancellation_details.reason}")
            
#             if cancellation_details.reason == speechsdk.CancellationReason.Error:
#                 logger.error(f"Error details: {cancellation_details.error_details}")
#                 if is_streaming:
#                     logger.info("Attempting to restart speech recognition")
#                     try:
#                         speech_recognizer.stop_continuous_recognition()
#                         time.sleep(1)
#                         speech_recognizer.start_continuous_recognition()
#                     except Exception as e:
#                         logger.error(f"Reconnection attempt failed: {str(e)}")

#         def recognized_cb(evt):
#             try:
#                 text = evt.result.text
#                 if text.strip():
#                     logger.info(f"Speech recognized: {text}")
#                     transcription_queue.put({'text': text, 'is_final': True})
#                     asyncio.run(handle_translation(text))
#             except Exception as e:
#                 logger.error(f"Recognition callback error: {str(e)}")

#         def recognizing_cb(evt):
#             try:
#                 text = evt.result.text
#                 if text.strip():
#                     logger.debug(f"Speech recognizing: {text}")
#                     transcription_queue.put({'text': text, 'is_final': False})
#             except Exception as e:
#                 logger.error(f"Recognizing callback error: {str(e)}")

#         # Connect event handlers
#         speech_recognizer.recognized.connect(recognized_cb)
#         speech_recognizer.recognizing.connect(recognizing_cb)
#         speech_recognizer.session_started.connect(handle_session_started)
#         speech_recognizer.session_stopped.connect(handle_session_stopped)
#         speech_recognizer.canceled.connect(handle_canceled)

#         logger.info("Starting continuous recognition")
#         speech_recognizer.start_continuous_recognition()
        
#         # Initialize audio streaming
#         pyaudio_instance = pyaudio.PyAudio()
#         audio_stream = pyaudio_instance.open(
#             format=FORMAT,
#             channels=CHANNELS,
#             rate=RATE,
#             input=True,
#             frames_per_buffer=CHUNK
#         )
#         logger.info("Audio stream opened successfully")
        
#         global is_streaming
#         while is_streaming:
#             try:
#                 data = audio_stream.read(CHUNK, exception_on_overflow=False)
#                 audio_queue.put(data)
#             except Exception as e:
#                 logger.error(f"Audio stream error: {str(e)}")
#                 time.sleep(0.1)
                
#     except Exception as e:
#         logger.error(f"Fatal error in stream_audio: {str(e)}", exc_info=True)
#     finally:
#         logger.info("Cleaning up audio resources")
#         try:
#             if audio_stream:
#                 audio_stream.stop_stream()
#                 audio_stream.close()
#             if pyaudio_instance:
#                 pyaudio_instance.terminate()
#             if speech_recognizer:
#                 speech_recognizer.stop_continuous_recognition()
#         except Exception as cleanup_error:
#             logger.error(f"Error during cleanup: {str(cleanup_error)}")

# @app.errorhandler(404)
# def not_found(e):
#     app.logger.error(f"404 Error for URL: {request.url}")
#     return "Not found", 404

# # Add this debugger to see which URL is causing the 404
# @app.before_request
# def log_request():
#     app.logger.info(f'Request URL: {request.url}')

# if __name__ == '__main__':
#     try:
#         if not is_running_from_reloader():
#             logger.info("Starting Flask application")
            
#             # Create static directory if it doesn't exist
#             static_dir = os.path.join(app.root_path, 'static')
#             if not os.path.exists(static_dir):
#                 os.makedirs(static_dir)
#                 logger.info(f"Created static directory: {static_dir}")
        
#         app.run(debug=True, port=4585, threaded=True)
#     except Exception as e:
#         logger.error(f"Application startup error: {str(e)}", exc_info=True)
#         cleanup()

#============================================================================================================================================


####### Part 1 - Main Application Setup and Configurations  ######


from flask import Flask, render_template, request, jsonify, Response, make_response
from flask_cors import CORS
import azure.cognitiveservices.speech as speechsdk
from azure.cognitiveservices.speech import SpeechConfig
import queue
import logging
import json
import pyaudio
import uuid
import os
import tempfile
import time
from datetime import datetime
from cachetools import TTLCache, LRUCache
from collections import deque
import sys
import signal
from waitress import serve
from concurrent.futures import ThreadPoolExecutor
from werkzeug.serving import is_running_from_reloader
from functools import lru_cache
import aiohttp
import werkzeug.serving
from werkzeug.middleware.shared_data import SharedDataMiddleware
from werkzeug.serving import WSGIRequestHandler
from threading import Lock, Thread

executor = ThreadPoolExecutor(max_workers=10)

# Configure logging
log_directory = "logs"
if not os.path.exists(log_directory):
    os.makedirs(log_directory)

current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
file_handler = logging.FileHandler(f'{log_directory}/app_{current_time}.log')
console_handler = logging.StreamHandler(sys.stdout)

log_format = logging.Formatter('%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d - %(message)s')
file_handler.setFormatter(log_format)
console_handler.setFormatter(log_format)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.addHandler(file_handler)
logger.addHandler(console_handler)

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

class CustomRequestHandler(WSGIRequestHandler):
    def handle_error(self):
        try:
            super().handle_error()
        except OSError as e:
            if e.winerror == 10038:  # Socket error
                logger.error("Socket error occurred, attempting to recover")
            else:
                raise

app.wsgi_app = SharedDataMiddleware(app.wsgi_app, {})
werkzeug.serving.WSGIRequestHandler = CustomRequestHandler

# TRanslator Configuration (PAYG)
TRANSLATOR_KEY = "2BfzkpmTCXpbQlrNHAAOsG5MiaThHsCIvRVkVzGgC61r4pZNAk1uJQQJ99AKACYeBjFXJ3w3AAAbACOG5IFN"
TRANSLATOR_ENDPOINT = "https://api.cognitive.microsofttranslator.com"
TRANSLATOR_LOCATION = "eastus"  

# Azure Speech Service configuration (Free Tier)
#speech_key, service_region = "kB8Tt5fBgJt7r1hz4P98qx5tq55I0gvugyjhfAzPyBmHTddnN6WJJQQJ99AJACL93NaXJ3w3AAAYACOGPMpm", "australiaeast"

# Azure Speech Service configuration (PAYG Tier)
speech_key, service_region = "95zWlKeL0A5mbmIMYnrqBnudN2ImNK8jrnLM6Eq6zRwOQpA8r5FYJQQJ99AJACqBBLyXJ3w3AAAYACOGDrlz", "southeastasia"

# Enhanced caching system
translation_cache = TTLCache(maxsize=200000, ttl=24*360000)  # 24 hours cache
recent_translations = LRUCache(maxsize=10000)  # Recent translations cache
translation_lock = Lock()

# Rate limiting and debouncing
translation_rate_limit = {
    'requests': deque(maxlen=10000),
    'limit': 10000,
    'window': 60
}
last_translation_time = {}
DEBOUNCE_DELAY = 1.0  # 1 second delay

# Global variables
is_streaming = False
transcription_queue = queue.Queue()
audio_queue = queue.Queue()
connected_clients = {}
cleanup_done = False

# Audio settings
CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000



#######  Part 2: Core Functions (translation, normalization, client management  ########



def check_client_connections():
    """Periodically check and log client connection status"""
    while True:
        try:
            current_clients = list(connected_clients.keys())
            logger.info(f"Active clients: {current_clients}")
            for client_id in current_clients:
                if client_id not in connected_clients:
                    logger.warning(f"Client {client_id} disconnected")
            time.sleep(30)  # Check every 30 seconds
        except Exception as e:
            logger.error(f"Error checking client connections: {str(e)}")

# Start the connection checker in a separate thread
Thread(target=check_client_connections, daemon=True).start()

@lru_cache(maxsize=1000)
def normalize_text(text):
    """Normalize text to reduce duplicate translations"""
    return ' '.join(text.lower().split())

def send_translation_to_client(client_id, translation, is_final):
    """Send translation to client through queue"""
    try:
        if client_id in connected_clients:
            logger.debug(f"Sending translation to client {client_id}: {translation}")
            translation_queue = connected_clients[client_id]['translation_queue']
            message = {
                'type': 'final' if is_final else 'partial',
                'translation': translation
            }
            translation_queue.put(message)
            logger.debug(f"Translation sent successfully to client {client_id}")
        else:
            logger.warning(f"Client {client_id} not found in connected_clients")
    except Exception as e:
        logger.error(f"Error sending translation to client {client_id}: {str(e)}")

async def translate_text(text, target_language):
    """Perform the actual translation"""
    logger.info(f"Starting translation request - Text: '{text}', Target language: {target_language}")
    
    language_map = {
        'es': 'es',
        'en': 'en',
        'pt': 'pt-BR',
        'yue': 'yue-CN',  # Simplified Chinese
        'id': 'id'
    }
    
    target_lang = language_map.get(target_language)
    if not target_lang:
        logger.error(f"Invalid target language requested: {target_language}")
        raise ValueError(f"Invalid target language: {target_language}")

    endpoint = f'{TRANSLATOR_ENDPOINT}/translate'
    params = {
        'api-version': '3.0',
        'to': target_lang
    }
    headers = {
        'Ocp-Apim-Subscription-Key': TRANSLATOR_KEY,
        'Ocp-Apim-Subscription-Region': TRANSLATOR_LOCATION,
        'Content-type': 'application/json'
    }
    body = [{
        'text': text
    }]

    try:
        async with aiohttp.ClientSession() as session:
            logger.debug(f"Making API request to {endpoint}")
            logger.debug(f"Request params: {params}")
            logger.debug(f"Request body: {body}")
            
            async with session.post(endpoint, params=params, headers=headers, json=body) as response:
                logger.debug(f"Response status: {response.status}")
                response.raise_for_status()
                
                result = await response.json()
                logger.debug(f"Raw API response: {result}")
                
                translation = result[0]['translations'][0]['text']
                logger.debug(f"Extracted translation: {translation}")
                logger.info(f"Translation completed successfully - Original: '{text}' -> Translation: '{translation}' ({target_language})")
                return translation
    except aiohttp.ClientError as e:
        logger.error(f"API request failed: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error during translation: {str(e)}")
        raise

def safe_delete_file(filepath, max_retries=3, delay=0.1):
    """Safely delete a file with retries."""
    for attempt in range(max_retries):
        try:
            if os.path.exists(filepath):
                os.unlink(filepath)
                return True
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(delay)
                continue
            logger.warning(f"Failed to delete file {filepath} after {max_retries} attempts: {str(e)}")
            return False
    return False




#######  Part 3: Route Handlers (Flask routes)  ########


# Route Handlers

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/go_live')
def go_live():
    logger.info("Go live page requested")
    return render_template('go_live1.html')

@app.route('/join_live')
def join_live():
    logger.info("Join live page requested")
    return render_template('join_live.html')

@app.route('/translate_realtime', methods=['POST'])
async def translate_realtime():
    logger.info("Real-time translation endpoint called")
    try:
        data = request.get_json()
        text = data.get('text', '').strip()
        target_language = data.get('targetLanguage', '')
        client_id = data.get('clientId')
        is_final = data.get('isFinal', False)

        logger.debug(f"Received translation request - Text: '{text}', Target: {target_language}, Client: {client_id}, Final: {is_final}")

        if not text or not target_language or not client_id:
            logger.debug("Missing required parameters")
            return jsonify({'success': True})

        if not is_final:
            logger.debug("Skipping non-final transcription")
            return jsonify({'success': True})

        normalized_text = normalize_text(text)
        logger.debug(f"Normalized text: '{normalized_text}'")

        current_time = time.time()
        client_key = f"{client_id}:{target_language}"
        if client_key in last_translation_time:
            time_since_last = current_time - last_translation_time[client_key]
            logger.debug(f"Time since last translation for {client_key}: {time_since_last}s")
            if time_since_last < DEBOUNCE_DELAY:
                logger.debug(f"Debouncing translation request for {client_key}")
                return jsonify({'success': True})

        last_translation_time[client_key] = current_time

        cache_key = f"{normalized_text}:{target_language}"
        logger.debug(f"Checking cache with key: {cache_key}")
        
        if cache_key in recent_translations:
            logger.debug("Translation found in recent cache")
            translation = recent_translations[cache_key]
            send_translation_to_client(client_id, translation, is_final)
            return jsonify({'success': True})

        if cache_key in translation_cache:
            logger.debug("Translation found in main cache")
            translation = translation_cache[cache_key]
            recent_translations[cache_key] = translation
            send_translation_to_client(client_id, translation, is_final)
            return jsonify({'success': True})

        logger.debug("No cache hit, proceeding with translation")
        retries = 3
        for attempt in range(retries):
            try:
                translation = await translate_text(normalized_text, target_language)
                
                with translation_lock:
                    translation_cache[cache_key] = translation
                    recent_translations[cache_key] = translation
                
                send_translation_to_client(client_id, translation, is_final)
                return jsonify({'success': True})
            except Exception as e:
                if attempt == retries - 1:
                    logger.error(f"Translation failed after {retries} attempts: {str(e)}")
                    return jsonify({'error': str(e)}), 500
                logger.warning(f"Translation attempt {attempt + 1} failed: {str(e)}, retrying...")
                time.sleep(1)

    except Exception as e:
        logger.error(f"Translation endpoint error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/stream_transcription')
def stream_transcription():
    logger.info("New transcription stream connection established")
    def generate():
        logger.debug("Starting transcription stream generator")
        while True:
            try:
                item = transcription_queue.get(timeout=1)
                transcription = item.get('text', '')
                is_final = item.get('is_final', False)
                logger.debug(f"Sending transcription: {transcription} (is_final: {is_final})")
                yield f"data: {json.dumps({'transcription': transcription, 'is_final': is_final})}\n\n"
            except queue.Empty:
                yield f"data: {json.dumps({'keepalive': True})}\n\n"
            except Exception as e:
                logger.error(f"Error in transcription stream: {str(e)}")
                break

    response = Response(generate(), mimetype='text/event-stream')
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['X-Accel-Buffering'] = 'no'
    response.headers.pop('Connection', None)
    return response

@app.route('/stream_translation/<string:lang>')
def stream_translation(lang):
    client_id = request.args.get('client_id')
    logger.info(f"New translation stream connection for client: {client_id}, language: {lang}")

    valid_languages = ['en', 'es', 'pt', 'yue', 'id']
    if lang not in valid_languages:
        logger.error(f"Invalid language code requested: {lang}")
        return jsonify({'error': 'Invalid language code'}), 400

    def generate():
        try:
            if client_id not in connected_clients:
                logger.info(f"Creating new client connection: {client_id}")
                connected_clients[client_id] = {
                    'target_language': lang,
                    'translation_queue': queue.Queue(),
                    'last_active': time.time()
                }

            translation_queue = connected_clients[client_id]['translation_queue']

            while True:
                try:
                    message = translation_queue.get(timeout=1)
                    connected_clients[client_id]['last_active'] = time.time()
                    logger.debug(f"Sending message to client {client_id}: {message}")
                    yield f"data: {json.dumps(message)}\n\n"
                except queue.Empty:
                    if time.time() - connected_clients[client_id]['last_active'] > 30:
                        logger.warning(f"Client {client_id} connection timed out")
                        break
                    yield f"data: {json.dumps({'keepalive': True})}\n\n"
                except GeneratorExit:
                    logger.info(f"Client {client_id} disconnected")
                    if client_id in connected_clients:
                        del connected_clients[client_id]
                    break
        except Exception as e:
            logger.error(f"Error in translation stream for client {client_id}: {str(e)}")
            if client_id in connected_clients:
                del connected_clients[client_id]

    response = Response(generate(), mimetype='text/event-stream')
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['X-Accel-Buffering'] = 'no'
    response.headers.pop('Connection', None)
    return response

@app.route('/start_stream', methods=['POST'])
def start_stream():
    global is_streaming
    if not is_streaming:
        is_streaming = True
        executor.submit(stream_audio)
    return jsonify({"status": "started"})


@app.route('/stop_stream', methods=['POST'])
def stop_stream():
    """Stop all streaming and processing"""
    global is_streaming
    try:
        logger.info("Stopping stream processing")
        is_streaming = False
        
        # Clear transcription queue
        while not transcription_queue.empty():
            try:
                transcription_queue.get_nowait()
            except queue.Empty:
                break
        
        # Clear audio queue
        while not audio_queue.empty():
            try:
                audio_queue.get_nowait()
            except queue.Empty:
                break
        
        # Notify all connected clients
        for client_id in list(connected_clients.keys()):
            try:
                if client_id in connected_clients:
                    connected_clients[client_id]['translation_queue'].put({
                        'type': 'final',
                        'translation': ''
                    })
            except Exception as e:
                logger.error(f"Error notifying client {client_id}: {str(e)}")
        
        logger.info("Stream stopped successfully")
        return jsonify({"status": "stopped"})
    except Exception as e:
        logger.error(f"Error stopping stream: {str(e)}")
        return jsonify({'error': str(e)}), 500


#######  Part 4: Speech Recognition and Audio Streaming  ########



# Speech Recognition and Audio Streaming

def stream_audio():
    """Handle continuous speech recognition and audio streaming"""
    global is_streaming
    speech_recognizer = None
    stream = None
    p = None
    
    try:
        logger.info("Initializing speech recognition")
        speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=service_region)
        speech_config.speech_recognition_language = "en-US"
        audio_config = speechsdk.audio.AudioConfig(use_default_microphone=True)
        
        speech_recognizer = speechsdk.SpeechRecognizer(
            speech_config=speech_config, 
            audio_config=audio_config
        )

        def recognized_cb(evt):
            if is_streaming:  # Only process if still streaming
                try:
                    text = evt.result.text
                    logger.info(f"Speech recognized: {text}")
                    logger.debug(f"Recognition result details: {evt.result}")
                    transcription_queue.put({'text': text, 'is_final': True})
                except Exception as e:
                    logger.error(f"Error in recognition callback: {str(e)}")

        def recognizing_cb(evt):
            if is_streaming:  # Only process if still streaming
                try:
                    text = evt.result.text
                    logger.debug(f"Speech recognizing: {text}")
                    logger.debug(f"Recognition interim details: {evt.result}")
                    transcription_queue.put({'text': text, 'is_final': False})
                except Exception as e:
                    logger.error(f"Error in recognizing callback: {str(e)}")

        def canceled_cb(evt):
            logger.warning(f"Speech recognition canceled: {evt.result.cancellation_details}")
            
        speech_recognizer.recognized.connect(recognized_cb)
        speech_recognizer.recognizing.connect(recognizing_cb)
        speech_recognizer.canceled.connect(canceled_cb)

        logger.info("Starting continuous recognition")
        speech_recognizer.start_continuous_recognition()
        
        try:
            p = pyaudio.PyAudio()
            stream = p.open(
                format=FORMAT,
                channels=CHANNELS,
                rate=RATE,
                input=True,
                frames_per_buffer=CHUNK
            )
            
            logger.info("Audio stream started")
            while is_streaming:
                try:
                    data = stream.read(CHUNK, exception_on_overflow=False)
                    audio_queue.put(data)
                except Exception as e:
                    logger.error(f"Error reading audio stream: {str(e)}", exc_info=True)
                    break
                
        except Exception as e:
            logger.error(f"Error in audio stream setup: {str(e)}", exc_info=True)
        finally:
            if stream:
                stream.stop_stream()
                stream.close()
            if p:
                p.terminate()
            
    except Exception as e:
        logger.error(f"Critical error in stream_audio: {str(e)}", exc_info=True)
    finally:
        if speech_recognizer:
            try:
                speech_recognizer.stop_continuous_recognition()
                logger.info("Speech recognition stopped")
            except Exception as e:
                logger.error(f"Error stopping speech recognition: {str(e)}")
        
        # Clear the audio queue
        while not audio_queue.empty():
            try:
                audio_queue.get_nowait()
            except queue.Empty:
                break

@app.route('/synthesize_speech', methods=['POST'])
def synthesize_speech():
    temp_file = None
    temp_filename = None
    
    try:
        data = request.get_json()
        text = data.get('text')
        language = data.get('language')

        logger.info(f"Speech synthesis requested - Text: '{text}', Language: {language}")

        if not text:
            logger.error("No text provided for speech synthesis")
            return jsonify({'error': 'No text provided'}), 400

        speech_config = SpeechConfig(
            subscription=speech_key,
            region=service_region
        )

        if language == 'pt':
            speech_config.speech_synthesis_voice_name = "pt-BR-AntonioNeural"
        elif language == 'es':
            speech_config.speech_synthesis_voice_name = "es-ES-AlvaroNeural"
        elif language == 'yue':
            speech_config.speech_synthesis_voice_name = "yue-CN-YunSongNeural"
        elif language == 'id':
            speech_config.speech_synthesis_voice_name = "id-ID-ArdiNeural"
        else:
            logger.error(f"Unsupported language for speech synthesis: {language}")
            return jsonify({'error': 'Unsupported language'}), 400

        temp_dir = tempfile.gettempdir()
        temp_filename = os.path.join(temp_dir, f'speech_{uuid.uuid4()}.wav')
        logger.debug(f"Created temporary file: {temp_filename}")
        
        audio_config = speechsdk.audio.AudioOutputConfig(filename=temp_filename)
        
        synthesizer = speechsdk.SpeechSynthesizer(
            speech_config=speech_config,
            audio_config=audio_config
        )

        logger.debug("Starting speech synthesis")
        result = synthesizer.speak_text_async(text).get()

        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            try:
                with open(temp_filename, 'rb') as audio_file:
                    audio_data = audio_file.read()

                response = make_response(audio_data)
                response.headers['Content-Type'] = 'audio/wav'
                response.headers['Content-Disposition'] = 'attachment; filename=speech.wav'
                
                synthesizer = None
                logger.info("Speech synthesis completed successfully")
                return response
                
            except Exception as e:
                logger.error(f"Error reading synthesized audio file: {str(e)}")
                return jsonify({'error': 'Failed to read audio file'}), 500
        else:
            error_details = result.cancellation_details
            logger.error(f"Speech synthesis failed: {error_details.error_details}")
            return jsonify({
                'error': 'Speech synthesis failed',
                'details': error_details.error_details
            }), 500

    except Exception as e:
        logger.error(f"Speech synthesis error: {str(e)}")
        return jsonify({'error': str(e)}), 500

    finally:
        try:
            if 'synthesizer' in locals() and synthesizer:
                synthesizer = None
            
            if temp_filename:
                logger.debug(f"Cleaning up temporary file: {temp_filename}")
                safe_delete_file(temp_filename)
        except Exception as e:
            logger.warning(f"Cleanup error: {str(e)}")




#######  Part 5: Cleanup and Main Application Entry  ########


# Cleanup and Main Entry

def cleanup():
    """Clean up resources before shutdown"""
    global is_streaming, cleanup_done
    if not cleanup_done:
        logger.info("Cleaning up resources...")
        is_streaming = False
        
        # Close all event sources
        for client_id in list(connected_clients.keys()):
            try:
                if client_id in connected_clients:
                    logger.debug(f"Cleaning up client: {client_id}")
                    del connected_clients[client_id]
            except Exception as e:
                logger.error(f"Error cleaning up client {client_id}: {e}")

        # Shutdown executor
        try:
            logger.debug("Shutting down executor")
            executor.shutdown(wait=False)
        except Exception as e:
            logger.error(f"Error shutting down executor: {e}")

        # Clear queues
        try:
            logger.debug("Clearing queues")
            while not audio_queue.empty():
                audio_queue.get_nowait()
            while not transcription_queue.empty():
                transcription_queue.get_nowait()
        except Exception as e:
            logger.error(f"Error clearing queues: {e}")

        cleanup_done = True
        logger.info("Cleanup completed")

def signal_handler(signum, frame):
    """Handle system signals"""
    logger.info(f"Received signal {signum}")
    cleanup()
    sys.exit(0)

# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

app.config['SERVER_NAME'] = None  
app.config['PREFERRED_URL_SCHEME'] = 'https'

if __name__ == '__main__':
    try:
        logger.info("Starting Flask application")
        if not is_running_from_reloader():
            # Run with waitress
            logger.info("Starting with Waitress server")
            serve(app, host='0.0.0.0', port=4585, threads=8,
                  url_scheme='http', channel_timeout=300,
                  cleanup_interval=30, outbuf_overflow=104857600)
        else:
            # Run in debug mode
            logger.info("Starting in debug mode")
            app.run(host='0.0.0.0', port=5000, debug=True)
    except Exception as e:
        logger.error(f"Application startup error: {str(e)}", exc_info=True)
        cleanup()
