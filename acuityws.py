from gtts import gTTS
import os
from pyowm import OWM
from pysstv.sstv import SSTV
from pysstv.color import Robot36
from PIL import Image
import pygame.camera
from time import sleep
from datetime import datetime
import pyaudio
import numpy as np
import struct
import math
import vlc
import audioread

# User Configuration
WEBCAM_DEVICE_NAME = "[DEVICE NAME OF YOUR CAMERA]"
OPENWEATHERMAP_API_KEY = "[YOUR FREE OPENWEATHERMAP API KEY]"
FFT_NOISE_REJECTION = 70 # Noise rejection factor (50-100 usually works the best)


# Program constants - shouldn't need to be modified
FORMAT = pyaudio.paInt16 # 32 bit signed
CHANNELS = 1 # Mono input
RATE = 44100 # Input sample rate (44100 is the default for most pcs)
INPUT_BLOCK_TIME = 0.05 # Input sample time in seconds for FFT (1/20s alternating sample period)
INPUT_FRAMES_PER_BLOCK = int(RATE*INPUT_BLOCK_TIME)
DTMF_FREQ_TOLERANCE = 5 # Tolerance in Hz for DTMF
DTMF_FREQS = { # Standard DTMF frequencies for 0-9, * and #
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

def fftContains(fftArr, freq): # Find a frequency in a FFT array
    for i in range(freq - DTMF_FREQ_TOLERANCE, freq + DTMF_FREQ_TOLERANCE):
        return (i in fftArr)

def wait_for_DTMF():
    pa = pyaudio.PyAudio()
    
    # Dump frames to prevent duplication
    stream = pa.open(format=FORMAT, channels=CHANNELS,
            rate=RATE, input=True,
            frames_per_buffer=INPUT_FRAMES_PER_BLOCK)
    data = stream.read(INPUT_FRAMES_PER_BLOCK)
    stream.close()

    # Listen for tone
    while (True):
        frames = []
        expFrames = []
        dtmfChar = ""
        chunkFFT = []

        stream = pa.open(format=FORMAT, channels=CHANNELS,
            rate=RATE, input=True,
            frames_per_buffer=INPUT_FRAMES_PER_BLOCK)
        
        for i in range(0, int(INPUT_FRAMES_PER_BLOCK)): # Get input audio
            data = stream.read(1)
            frames.append(data)
        stream.close()
        
        for i in range(0, len(frames)): # Format audio for FFT
            sFrame = frames[i]
            expFrames.append(struct.unpack("<h", sFrame)[0])
            
        chunkFFT = np.fft.fft(expFrames, 44100) # Apply FFT to audio

        for i in range(len(chunkFFT)): # Convert to integers
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

def wait_for_no_DTMF():
    pa = pyaudio.PyAudio()
    
    # Dump frames to prevent duplication
    stream = pa.open(format=FORMAT, channels=CHANNELS,
            rate=RATE, input=True,
            frames_per_buffer=INPUT_FRAMES_PER_BLOCK)
    data = stream.read(INPUT_FRAMES_PER_BLOCK)
    stream.close()

    # Listen for lack of tone
    while (True):
        frames = []
        expFrames = []
        dtmfChar = ""
        chunkFFT = []

        stream = pa.open(format=FORMAT, channels=CHANNELS,
            rate=RATE, input=True,
            frames_per_buffer=INPUT_FRAMES_PER_BLOCK)
        
        for i in range(0, int(INPUT_FRAMES_PER_BLOCK)): # Get input audio
            data = stream.read(1)
            frames.append(data)
        stream.close()
        
        for i in range(0, len(frames)): # Format audio for FFT
            sFrame = frames[i]
            expFrames.append(struct.unpack("<h", sFrame)[0])
            
        chunkFFT = np.fft.fft(expFrames, 44100) # Apply FFT to audio

        for i in range(len(chunkFFT)): # Convert to integers
            chunkFFT[i] = int(np.absolute(chunkFFT[i]))
            
        noiseCeiling = FFT_NOISE_REJECTION * np.average(chunkFFT) # Calculate noise ceiling

        denoisedFreqs = []
        for i in range(len(chunkFFT)): # Pull clean frequencies from FFT
            if (chunkFFT[i] > noiseCeiling):
                denoisedFreqs.append(i)
        
        discoveredPairs = 0 # See if there's a tone pair
        for dtmfChar, dtmfPair in DTMF_FREQS.items(): 
            if (fftContains(denoisedFreqs, dtmfPair[0]) and 
                fftContains(denoisedFreqs, dtmfPair[1])):
                discoveredPairs += 1
        if(discoveredPairs == 0):
            pa.terminate()
            break

def getWeather(place):
    owm = OWM(OPENWEATHERMAP_API_KEY)
    mgr = owm.weather_manager()
    observation = mgr.weather_at_place(place)
    return observation.weather

def speak(text):
    tts = gTTS(text=text, lang='en')
    tts.save("audio/cache/cache.mp3")
    playSound("audio/cache/cache.mp3")

def getSSTV():
    pygame.camera.init()
    cam = pygame.camera.Camera(WEBCAM_DEVICE_NAME,(640,480))
    cam.start()
    sleep(1)  # Let camera start & focus
    img = cam.get_image()
    pygame.image.save(img,"audio/cache/webcam-cache.jpg")
    im = Image.open("audio/cache/webcam-cache.jpg")
    width, height = im.size
    newsize = (320, 240)
    img = im.resize(newsize)
    sstv = Robot36(img, 44100, 16)
    sstv.vox_enabled = True
    sstv.write_wav("audio/cache/cache.wav")

def playSound(filename):
    p = vlc.MediaPlayer(filename)
    p.play()
    with audioread.audio_open(filename) as f: # Wait for file to finish
        sleep(f.duration + 1)

def getDTMFinput(length):
    output = ""
    for i in range(length):
        output += wait_for_DTMF()
        output += " "
        wait_for_no_DTMF()
    playSound("audio/builtin/ack.wav")
    return output

def getVerifiedInput(length):
    playSound("audio/builtin/inputinfo.mp3")
    while(True):
        speak("Input format is " + str(length) + " digits. ")
        playSound("audio/builtin/ack.wav")
        echoin = getDTMFinput(length)
        speak("You sent "+ str(echoin) + ".")
        playSound("audio/builtin/inputconf.mp3")
        playSound("audio/builtin/ack.wav")
        if(wait_for_DTMF() == "1"):
            return echoin
        elif(wait_for_DTMF() != "2"):
            return ""

print("acuityWS Alpha r1.0")
while(True):
    print("Listening for DTMF.")
    recd_dtmf = ""
    recd_dtmf = wait_for_DTMF()
    now = datetime.now()
    theTime = now.strftime("%H:%M")
    print ("DTMF tone " + recd_dtmf + " received at " + theTime + ".")
    sleep(2) # Wait for incoming transmission to stop
    playSound("audio/builtin/ack.wav")
    if(recd_dtmf == "1"):
        playSound("audio/builtin/menu.mp3")

    elif(recd_dtmf == "2"): # Weather data
        try:
            w = getWeather("Potsdam,US")
            spokenString = "The time is " + theTime + ". "
            spokenString += "Weather " + w.detailed_status + ". Temp " + str(int(w.temperature('fahrenheit').get("temp"))) + " degrees. "
            spokenString += "Wind " + str(int(w.wind().get("speed") * 1.944)) + " knots. Humidity " + str(w.humidity) + " percent."
            speak(spokenString)
        except:
            playSound("audio/builtin/error.mp3")

    elif(recd_dtmf == "3"): # Live SSTV
        try:
            getSSTV()
            playSound("audio/cache/cache.wav")
        except:
            playSound("audio/builtin/error.mp3")

    elif(recd_dtmf == "*"): # SFX Easter Egg
        playSound("audio/builtin/singledigitprompt.mp3")
        playSound("audio/builtin/ack.wav")
        ee_dtmf = wait_for_DTMF()
        sleep(1)
        if(ee_dtmf == "1"):
            playSound("audio/builtin/sfx/1.mp3")
        elif(ee_dtmf == "2"):
            playSound("audio/builtin/sfx/2.mp3")
        elif(ee_dtmf == "3"):
            playSound("audio/builtin/sfx/3.mp3")
        else:
            playSound("audio/builtin/sfx/4.mp3")

    elif(recd_dtmf == "#"): # More Information
        playSound("audio/builtin/moreinfo.mp3")

    elif(recd_dtmf == "4"):
        playSound("audio/builtin/checkinInfo.mp3")
        echoin = getVerifiedInput(10)
        sleep(1)
        playSound("audio/builtin/checkinConf.mp3")
        with open("checkins.log", "a") as f:
            f.write("[" + now.strftime('%Y-%m-%d %H:%M:%S') + "] " + "".join(echoin.split()) + " checked in. \n")
    else: # Default to menu (1)
        playSound("audio/builtin/menu.mp3")
    playSound("audio/builtin/end.wav")
    sleep(5) # Transmission cooldown
