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
    confLines = []
    for i in f.readlines():
        if(i[0] != "#"):
            confLines.append(i.split("=")[1].strip("\n"))
WEBCAM_DEVICE_INDEX = int(confLines[0])
OPENWEATHERMAP_API_KEY = confLines[1]
OWM_WEATHER_CITY_NAME = confLines[2]

################################################################ PROGRAM CONSTANTS (Should not need to be modified)
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 44100
INPUT_BLOCK_TIME = 0.1
INPUT_FRAMES_PER_BLOCK = int(RATE*INPUT_BLOCK_TIME)
DTMF_FREQ_TOLERANCE = 5
FFT_NOISE_REJECTION = 80

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
CLIPS = {
    # General (beeps, menus, errors)
    "ack" : "audio/builtin/ack.wav",                                 # Acknowledgement beep
    "end" : "audio/builtin/end.wav",                                 # End transmission beep
    "mainMenu" : "audio/builtin/menu.mp3",                           # Main menu
    "moreInfo" : "audio/builtin/moreinfo.mp3",                       # More information about the station
    "inputConf" : "audio/builtin/inputconf.mp3",                     # Input confirmation
    "crash" : "audio/builtin/crash.mp3",                             # Server crash warning
    "apiError" : "audio/builtin/error.mp3",                          # Non-fatal error warning
    "singleDigitPrompt" : "audio/builtin/singledigitprompt.mp3",     # Prompt the user for a single digit
    "loginTFA" : "audio/builtin/voicemail/loginTFA.mp3",             # Prompt user for two-factor auth code.
    "invalidTFA" : "audio/builtin/voicemail/tfainvalid.mp3",         # If user's TFA code is invalid.
    # Sound effects
    "sfx1" : "audio/builtin/sfx/1.mp3",
    "sfx2" : "audio/builtin/sfx/2.mp3",
    "sfx3" : "audio/builtin/sfx/3.mp3",
    "sfx4" : "audio/builtin/sfx/4.mp3",



}
################################################################################ LOGGING
def getDateAndTime(): # Long date and time for logging
        now = datetime.now()
        return now.strftime('%Y-%m-%d %H:%M:%S')

# Logging level (0: INFO, 1: WARN (recommended), 2: ERROR, 3: FATAL, 4: NONE)
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
        f.write(getDateAndTime() + " [  OK  ] " + LOG_PREFIX + " Logging initialized.\n")

def log(level: int, data: str):
    if(level >= LOG_LEVEL):
        output = getDateAndTime()
        if(level == 0):
            output += " [  OK  ] "
        elif(level == 1):
            output += " [ WARN ] "
        elif(level == 2):
            output += " [ CAUT ] "
        else:
            output += " [[ ERROR ]] "
        output += LOG_PREFIX + " "
        output += data
        if(LOG_TO_FILE):
            with open(LOG_PATH, "a") as f:
                f.write(output + "\n")
        if(LOG_TO_CONSOLE):
            print(output)

################################################################ AUDIO MANIPULATION
def recordAudio(outputFilename, length): # Record to a .wav file for a specified number of seconds
    pa = pyaudio.PyAudio()
    stream = pa.open(format=pyaudio.paInt16,
                    channels=1,
                    rate=44100,
                    frames_per_buffer=1024,
                    input=True)
    inFrames = []
    for i in range(0, int(44100 / 1024 * int(length))):
        data = stream.read(1024)
        inFrames.append(data)
    stream.stop_stream()
    stream.close()
    pa.terminate()
    with wave.open(outputFilename, 'wb') as f:
        f.setnchannels(1)
        f.setsampwidth(pa.get_sample_size(pyaudio.paInt16))
        f.setframerate(44100)
        f.writeframes(b''.join(inFrames))

def fftContains(fftArr, freq): # Find a specified frequency in a fourier transform
    for i in range(freq - DTMF_FREQ_TOLERANCE, freq + DTMF_FREQ_TOLERANCE):
        return (i in fftArr)

def wait_for_DTMF(timeout = -1): # Wait for and return the character represented by a DTMF tone.
    pa = pyaudio.PyAudio()
    # Flush buffer
    stream = pa.open(format=FORMAT, channels=CHANNELS,
            rate=RATE, input=True,
            frames_per_buffer=INPUT_FRAMES_PER_BLOCK)
    data = stream.read(INPUT_FRAMES_PER_BLOCK)
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
            if (fftContains(denoisedFreqs, dtmfPair[0]) and 
                fftContains(denoisedFreqs, dtmfPair[1])):
                pa.terminate() # Close pyAudio instance
                return dtmfChar

def speak(text): # Speak a line on the default audio device with gTTS
    tts = gTTS(text=text, lang='en')
    tts.save("audio/cache/cache.mp3")
    playSound("audio/cache/cache.mp3")

def playSound(filename): # Play a sound on the default audio device
    p = vlc.MediaPlayer(filename)
    p.play()
    with audioread.audio_open(filename) as f:
        sleep(f.duration + 1)

def getDTMFinput(length): # Get DTMF input of a specified number of ints
    output = ""
    for i in range(length):
        output += wait_for_DTMF()
        sleep(0.5)
    sleep(0.5)
    playSound(CLIPS.get("ack"))
    return output

def getVerifiedInput(length): # Get and confirm DTMF input of a specified number of ints
    while(True):
        playSound(CLIPS.get("ack"))
        echoin = getDTMFinput(length)
        speak("You sent " + " ".join(list(echoin)) + ".")
        playSound(CLIPS.get("inputConf"))
        playSound(CLIPS.get("ack"))
        userDTMF = wait_for_DTMF()
        if(userDTMF == "1"):
            return echoin
        elif(userDTMF == "2"):
            sleep(1)
        else:
            return ""

################################################################ DATA
def getWeather(place): # Get the weather observation from OWM at a specified location
    owm = OWM(OPENWEATHERMAP_API_KEY)
    mgr = owm.weather_manager()
    observation = mgr.weather_at_place(place)
    return observation.weather

def getSSTV(): # Take a picture, encode it to SSTV, and write it to a .wav file.
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

def getDateAndTime(): # Long date and time
        now = datetime.now()
        return now.strftime('%Y-%m-%d %H:%M:%S')

def getTime(): # Short time
        now = datetime.now()
        return now.strftime("%H:%M")

################################################################ MAIN LOOP
log(0, "Welcome to AcuityWS.")
crash_restart = False
while(True):
    try:
        # Notify listeners if a crash happens
        if(crash_restart): 
            playSound(CLIPS.get("crash"))
            crash_restart = False

        # Get and acknowledge initial input
        log(0, "DTMF listener started on default input device.")
        recd_dtmf = wait_for_DTMF()
        log(0, "Tone " + recd_dtmf + " received.")
        sleep(1) # Give incoming transmission time to stop
        playSound(CLIPS.get("ack"))

        ################################################################ MAIN MENU CHOICES
        if(recd_dtmf == "1"): # Play main menu
            log(0, "Playing main menu.")
            playSound(CLIPS.get("mainMenu"))

        elif(recd_dtmf == "2"): # Get TTS Weather data
            try: 
                w = getWeather(OWM_WEATHER_CITY_NAME)
                spokenString = "The time is " + getTime() + ". "
                spokenString += "Weather " + w.detailed_status + ". Temp " + str(int(w.temperature('fahrenheit').get("temp"))) + " degrees. "
                spokenString += "Wind " + str(int(w.wind().get("speed") * 1.944)) + " knots. Humidity " + str(w.humidity) + " percent."
                log(0, "Retrieved weather data: " + spokenString)
                speak(spokenString)
            except Exception as e:
                log(2, "Weather applet encountered an exception: " + str(e) + ".")
                playSound(CLIPS.get("apiError"))

        elif(recd_dtmf == "3"): # Get Live SSTV
            try:
                getSSTV()
                log(0, "Sent live SSTV image.")
                playSound("audio/cache/cache.wav")
            except Exception as e:
                log(2, "SSTV applet encountered an exception: " + str(e) + ".")
                playSound(CLIPS.get("apiError"))

        elif(recd_dtmf == "*"): # SFX Easter Egg
            log(0, "User is playing a sound effect.")
            playSound(CLIPS.get("singleDigitPrompt"))
            playSound(CLIPS.get("ack"))
            userOption = wait_for_DTMF()
            sleep(1)
            log(0, "Playing sound effect " + userOption)
            if(userOption == "1"):
                playSound(CLIPS.get("sfx1"))
            elif(userOption == "2"):
                playSound(CLIPS.get("sfx2"))
            elif(userOption == "3"):
                playSound(CLIPS.get("sfx3"))
            else:
                playSound(CLIPS.get("sfx4"))
        
        elif(recd_dtmf == "#"): # More Information
            log(0, "Playing more information.")
            playSound(CLIPS.get("moreInfo"))

        else: # Default to menu (1)
            log(1, "User choice " + recd_dtmf + " is invalid. Defaulting to main menu.")
            playSound(CLIPS.get("mainMenu"))

        # At the end of every transmission:
        playSound(CLIPS.get("end"))
        log(0, "Transmission ended.")
        sleep(5) # Transmission cooldown

################################################################ END MENU OPTIONS
    # We want the station to be up at all times, so if a fatal error happens, log it and restart.
    except Exception as e:
        log(3,"AcuityWS encountered a fatal exception: " + str(e) + "! Restarting...")
        crash_restart = True
        sleep(1) # prevent overload due to error looping