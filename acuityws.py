# Dependency imports
from gtts import gTTS
from pyowm import OWM
from PIL import Image
from pysstv.color import Robot36
import vlc
import audioread
import pygame.camera
import pyaudio
import numpy as np

# Builtin imports
import os
from time import sleep
from datetime import datetime
import struct
import wave

################################################################ USER CONSTANTS (Read from configuration file)
with open("acuityWS.conf","r") as f:
    conf_lines = []
    for i in f.readlines():
        if(i[0] != "#" and i[0] != " "):
            conf_lines.append(i.split("=")[1].strip("\n"))
WEBCAM_DEVICE_INDEX = int(conf_lines[0])
OPENWEATHERMAP_API_KEY = conf_lines[1]
WEATHER_LAT = float(conf_lines[2])
WEATHER_LON = float(conf_lines[3])

################################################################ PROGRAM CONSTANTS (Should not need to be modified)
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 44100
INPUT_BLOCK_TIME = 0.1
INPUT_FRAMES_PER_BLOCK = int(RATE*INPUT_BLOCK_TIME)
DTMF_FREQ_TOLERANCE = 5
FFT_NOISE_REJECTION = 80

# DTMF frequency pairs
DTMF_FREQS = {
    '1': [1209, 697],
    '2': [1336, 697],
    '3': [1477, 697],
    '4': [1209, 770],
    '5': [1336, 770],
    '6': [1477, 770],
    '7': [1209, 852],
    '8': [1336, 852],
    '9': [1477, 852],
    '0': [1336, 941],
    '*': [1209, 941],
    '#': [1477, 941],
}

# Sound clips
CLIPS = {
    "ack"          : "audio/builtin/ack.wav",         # Acknowledgement beep
    "end"          : "audio/builtin/end.wav",         # End transmission beep
    "main_menu"    : "audio/builtin/menu.mp3",        # Main menu
    "more_info"    : "audio/builtin/moreinfo.mp3",    # More information about the station
    "input_conf"   : "audio/builtin/inputconf.mp3",   # Input confirmation
    "input_prompt" : "audio/builtin/inputprompt.mp3", # Input prompt
    "crash"        : "audio/builtin/crash.mp3",       # Server crash warning
    "api_error"    : "audio/builtin/error.mp3",       # Non-fatal error warning
}

# Sound effects
SFX = {
    "1" : "audio/sfx/1.mp3",
    "2" : "audio/sfx/2.mp3",
    "3" : "audio/sfx/3.mp3",
    "4" : "audio/sfx/4.mp3",
    "5" : "audio/sfx/5.mp3",
    "6" : "audio/sfx/6.mp3",
    "7" : "audio/sfx/7.mp3",
    "8" : "audio/sfx/8.mp3",
    "9" : "audio/sfx/9.mp3",
    "0" : "audio/sfx/0.mp3",
}

################################################################################ LOGGING
def get_date_and_time(): # Long date and time for logging
        now = datetime.now()
        return now.strftime('%Y-%m-%d %H:%M:%S')

# Logging level (0: INFO, 1: WARN (recommended), 2: ERROR, 3: NONE)
LOG_LEVEL = 0
#
# Should the log output to the console?
LOG_TO_CONSOLE = True
#
# Should the log output to a log file?
LOG_TO_FILE = False
#
# Where to generate logfile if need be
LOG_PATH = "logs/acuityws.log"
#
# How the log identifies which module is logging.
LOG_PREFIX = "(AcuityWS)"

# Initialize log file if needed
if(LOG_TO_FILE):
    try:
        os.remove(LOG_PATH)
    except:
        pass
    with open(LOG_PATH, "w") as f:
        f.write(get_date_and_time() + " [  OK  ] " + LOG_PREFIX + " Logging initialized.\n")

def log(level: int, data: str):
    if(level >= LOG_LEVEL):
        output = get_date_and_time()
        if(level == 0):
            output += " [  OK  ] "
        elif(level == 1):
            output += " [ WARN ] "
        else:
            output += " [ ERR! ] "
        output += LOG_PREFIX + " "
        output += data
        if(LOG_TO_FILE):
            with open(LOG_PATH, "a") as f:
                f.write(output + "\n")
        if(LOG_TO_CONSOLE):
            print(output)

################################################################ AUDIO MANIPULATION

# Find a specified frequency in a fourier transform
def fft_contains(fft_arr, freq): 
    for i in range(freq - DTMF_FREQ_TOLERANCE, freq + DTMF_FREQ_TOLERANCE):
        return (i in fft_arr)

# Wait for and return the character represented by a DTMF tone.
def get_next_dtmf(timeout = -1): 
    pa = pyaudio.PyAudio()
    # Flush buffer
    stream = pa.open(format=FORMAT, channels=CHANNELS,
            rate=RATE, input=True,
            frames_per_buffer=INPUT_FRAMES_PER_BLOCK)
    stream.read(INPUT_FRAMES_PER_BLOCK)
    stream.stop_stream()
    stream.close()
    listenerDuration = 0
    while (True):
        listenerDuration += 1
        if(listenerDuration > timeout and timeout > 0):
            return ""

        expFrames = []
        dtmfChar = ""
        chunkFFT = []
        # Record
        stream = pa.open(format=FORMAT, channels=CHANNELS,
            rate=RATE, input=True,
            frames_per_buffer=INPUT_FRAMES_PER_BLOCK)
        frames = stream.read(INPUT_FRAMES_PER_BLOCK)
        stream.stop_stream()
        stream.close()

        # Format audio for FFT
        frameIter = 0
        while(frameIter < len(frames) - 1): 
            sFrame = frames[frameIter:frameIter+2]
            expFrames.append(struct.unpack("<h", sFrame)[0])
            frameIter += 2
            
        chunkFFT = np.fft.fft(expFrames, RATE) # Apply FFT

        for i in range(len(chunkFFT)): # Round FFT to real integers
            chunkFFT[i] = int(np.absolute(chunkFFT[i]))
            
        noiseCeiling = FFT_NOISE_REJECTION * np.average(chunkFFT) # Calculate noise ceiling

        denoisedFreqs = []
        for i in range(len(chunkFFT)): # Pull clean frequencies from FFT
            if (chunkFFT[i] > noiseCeiling):
                denoisedFreqs.append(i)

        for dtmfChar, dtmfPair in DTMF_FREQS.items(): # Get character from DTMF freqs
            if (fft_contains(denoisedFreqs, dtmfPair[0]) and 
                fft_contains(denoisedFreqs, dtmfPair[1])):
                pa.terminate() # Close pyAudio instance
                return dtmfChar

# Speak a line on the default audio device with gTTS
def speak_line(text): 
    tts = gTTS(text=text, lang='en')
    tts.save("audio/cache/cache.mp3")
    play_sound_file("audio/cache/cache.mp3")

# Play a sound on the default audio device
def play_sound_file(filename): 
    p = vlc.MediaPlayer(filename)
    p.play()
    with audioread.audio_open(filename) as f:
        sleep(f.duration + 1)

# Get DTMF input of a specified number of ints
def get_dtmf_input():
    play_sound_file(CLIPS.get("input_prompt"))
    output = ""
    while(i != "#"):
        output += get_next_dtmf()
        sleep(0.5)
    sleep(0.5)
    play_sound_file(CLIPS.get("ack"))
    return output

# Get and confirm DTMF input of a specified number of ints
def get_verified_input(length): 
    while(True):
        play_sound_file(CLIPS.get("input_prompt"))
        play_sound_file(CLIPS.get("ack"))
        echoin = get_dtmf_input(length)
        speak_line("You sent " + " ".join(list(echoin)) + ".")
        play_sound_file(CLIPS.get("input_conf"))
        play_sound_file(CLIPS.get("ack"))
        userDTMF = get_next_dtmf()
        if(userDTMF == "1"):
            return echoin
        elif(userDTMF == "2"):
            sleep(1)
        else:
            return ""

################################################################ DATA

# Get the weather observation from OWM at a specified location
def getWeather(lat, lon): 
    owm = OWM(OPENWEATHERMAP_API_KEY)
    mgr = owm.weather_manager()
    observation = mgr.weather_at_coords(lat, lon)
    return observation.weather

# Take a picture, encode it to SSTV, and write it to a .wav file.
def getSSTV(): 
    pygame.camera.init()
    cams = pygame.camera.list_cameras()
    log(0, "SSTV applet: " + str(len(cams)) + " cameras found.")
    log(0, "SSTV applet: Taking a picture with camera " + str(WEBCAM_DEVICE_INDEX) + ": " + cams[WEBCAM_DEVICE_INDEX])
    cam = pygame.camera.Camera(cams[WEBCAM_DEVICE_INDEX],(640,480))
    cam.start()
    sleep(1)  # Let camera start & focus
    img = cam.get_image()
    pygame.image.save(img,"audio/cache/cache.jpg")
    im = Image.open("audio/cache/cache.jpg")
    width, height = im.size
    newsize = (320, 240)
    img = im.resize(newsize)
    sstv = Robot36(img, 44100, 16)
    sstv.vox_enabled = True
    sstv.write_wav("audio/cache/cache.wav")

# Long date and time
def get_date_and_time(): 
        now = datetime.now()
        return now.strftime('%Y-%m-%d %H:%M:%S')

# Short time
def getTime():
        now = datetime.now()
        return now.strftime("%H:%M")

################################################################ MAIN LOOP
log(0, "Welcome to AcuityWS.")
crash_restart = False
while(True):
    try:
        # Notify listeners if a crash happens
        if(crash_restart): 
            play_sound_file(CLIPS.get("crash"))
            crash_restart = False

        # Get and acknowledge initial input
        log(0, "DTMF listener started on default input device.")
        recd_dtmf = get_next_dtmf()
        log(0, "Tone " + recd_dtmf + " received.")
        sleep(1) # Give incoming transmission time to stop
        play_sound_file(CLIPS.get("ack"))

        ################################################################ MAIN MENU CHOICES
        if(recd_dtmf == "1"): # Play main menu
            log(0, "Playing main menu.")
            play_sound_file(CLIPS.get("main_menu"))

        elif(recd_dtmf == "2"): # Get TTS Weather data
            try: 
                w = getWeather(WEATHER_LAT, WEATHER_LON)
                spokenString = "The time is " + getTime() + ". "
                spokenString += "Weather " + w.detailed_status + ". Temp " + str(int(w.temperature('fahrenheit').get("temp"))) + " degrees. "
                spokenString += "Wind " + str(int(w.wind().get("speed") * 1.944)) + " knots. Humidity " + str(w.humidity) + " percent."
                log(0, "Retrieved weather data: " + spokenString)
                speak_line(spokenString)
            except Exception as e:
                log(2, "Weather applet encountered an exception: " + str(e) + ".")
                play_sound_file(CLIPS.get("api_error"))

        elif(recd_dtmf == "3"): # Get live SSTV
            try:
                getSSTV()
                log(0, "Sent live SSTV image.")
                play_sound_file("audio/cache/cache.wav")
            except Exception as e:
                log(2, "SSTV applet encountered an exception: " + str(e) + ".")
                play_sound_file(CLIPS.get("api_error"))

        elif(recd_dtmf == "#"): # SFX Easter Egg
            log(0, "User is playing a sound effect.")
            userOption = get_dtmf_input()
            sleep(1)
            log(0, "Playing sound effect " + userOption)
            if(userOption == "1"):
                play_sound_file(SFX.get("1"))
            elif(userOption == "2"):
                play_sound_file(SFX.get("2"))
            elif(userOption == "3"):
                play_sound_file(SFX.get("3"))
            elif(userOption == "4"):
                play_sound_file(SFX.get("4"))
            elif(userOption == "5"):
                play_sound_file(SFX.get("5"))
            elif(userOption == "6"):
                play_sound_file(SFX.get("6"))
            elif(userOption == "7"):
                play_sound_file(SFX.get("7"))
            elif(userOption == "8"):
                play_sound_file(SFX.get("8"))
            elif(userOption == "9"):
                play_sound_file(SFX.get("9"))
            else:
                play_sound_file(SFX.get("0"))
        
        elif(recd_dtmf == "*"): # More Information
            log(0, "Playing more information.")
            play_sound_file(CLIPS.get("more_info"))

        else: # Default to menu (1)
            log(1, "User choice " + recd_dtmf + " is invalid. Defaulting to main menu.")
            play_sound_file(CLIPS.get("main_menu"))

        # At the end of every transmission:
        play_sound_file(CLIPS.get("end"))
        log(0, "Transmission ended.")
        sleep(5) # Transmission cooldown

################################################################ END MENU OPTIONS
    # We want the station to be up at all times, so if a fatal error happens, log it and restart.
    except Exception as e:
        log(3,"AcuityWS encountered a fatal exception: " + str(e) + "! Restarting...")
        crash_restart = True
        sleep(1) # prevent overload due to error looping