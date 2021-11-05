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

# Built-in imports
import os
from time import sleep
from datetime import datetime
import struct
import smtplib
from email.mime.text import MIMEText
import random
import wave

################################################################ USER CONFIG
WEBCAM_DEVICE_NAME = "xxxxxxxxxxxxxxxx"                        # Device name of the webcam used for SSTV.
OPENWEATHERMAP_API_KEY = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"    # Free API key from OpenWeatherMap.org
OWM_WEATHER_CITY_NAME = "xxxxxxxxxx"                           # OpenWeatherMap location for weather
SMTP_EMAIL_ADDRESS = "xxxxxxxxxxxxxxxxxx"                      # Sending email address for 2FA
SMTP_EMAIL_PASSWORD = "xxxxxxxxxxxxxxxx"                       # SMTP password for 2FA
SMTP_SERVER_ADDRESS = "xxxxxxxxxxxxxxxxxx"                     # SMTP server hostname
SMTP_SERVER_PORT = 123                                         # SMTP port number

################################################################ PROGRAM CONSTANTS
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 44100
INPUT_BLOCK_TIME = 0.1
INPUT_FRAMES_PER_BLOCK = int(RATE*INPUT_BLOCK_TIME)
DTMF_FREQ_TOLERANCE = 5
FFT_NOISE_REJECTION = 70
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
SMS_GATEWAYS = {
    "1" : "@txt.att.net",                     # AT&T or Cricket
    "2" : "@sms.myboostmobile.com",           # Boost Mobile
    "3" : "@mymetropcs.com",                  # MetroPCS
    "4" : "@msg.fi.google.com",               # Google Fi
    "5" : "@text.republicwireless.com" ,      # Republic Wireless
    "6" : "@messaging.sprintpcs.com",         # Sprint
    "7" : "@tmomail.net",                     # T-Mobile
    "8" : "@email.uscc.net",                  # US Cellular
    "9" : "@vtext.com",                       # Verizon Wireless
    "0" : "@vmobl.com"                        # Virgin Mobile
}

################################################################ SMTP
def sendMail(recipient, subject, message):
    msg = MIMEText(message)

    msg['Subject'] = subject
    msg['From'] = SMTP_EMAIL_ADDRESS
    msg['To'] = recipient
    
    try:
        with smtplib.SMTP(SMTP_SERVER_ADDRESS, SMTP_SERVER_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(SMTP_EMAIL_ADDRESS, SMTP_EMAIL_PASSWORD)
            server.sendmail(SMTP_EMAIL_ADDRESS, recipient, msg.as_string())
            server.quit()
        return True
    
    except Exception as e:
        print(e)
        return False

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

def wait_for_DTMF(): # Wait for and return the character represented by a DTMF tone.
    pa = pyaudio.PyAudio()

    # Flush buffer
    stream = pa.open(format=FORMAT, channels=CHANNELS,
            rate=RATE, input=True,
            frames_per_buffer=1024)
    data = stream.read(1024)
    stream.stop_stream()
    stream.close()

    while (True):
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
            
        chunkFFT = np.fft.fft(expFrames, 44100) # Apply FFT

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

def wait_for_no_DTMF(): # Wait for a DTMF tone to end to prevent duplication.
    pa = pyaudio.PyAudio()
    
    # Flush buffer
    stream = pa.open(format=FORMAT, channels=CHANNELS,
            rate=RATE, input=True,
            frames_per_buffer=1024)
    data = stream.read(1024)
    stream.stop_stream()
    stream.close()

    while (True):
        expFrames = []
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
        
        if(discoveredPairs == 0): # If there's not, then we're done.
            pa.terminate()
            break

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
        output += " "
        wait_for_no_DTMF()
    sleep(1)
    playSound("audio/builtin/ack.wav")
    return output

def getVerifiedInput(length): # Get and confirm DTMF input of a specified number of ints
    while(True):
        playSound("audio/builtin/ack.wav")
        echoin = getDTMFinput(length)
        speak("You sent "+ str(echoin) + ".")
        playSound("audio/builtin/inputconf.mp3")
        playSound("audio/builtin/ack.wav")
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

################################################################ MAIN LOOP
print("acuityWS Alpha r1.0")
crash_restart = False
while(True):
    try:
        # Notify users if a crash happens
        if(crash_restart): 
            playSound("audio/builtin/crash.mp3")
            crash_restart = False
        
        # Get and acknowledge initial input
        print("[INFO] DTMF listener started on default audio device.")
        recd_dtmf = wait_for_DTMF()
        now = datetime.now()
        theTime = now.strftime("%H:%M")
        print ("[INFO] DTMF tone " + recd_dtmf + " received at " + theTime + ".")
        sleep(1) # Give incoming transmission time to stop
        playSound("audio/builtin/ack.wav")

################################################################ MAIN MENU CHOICES
        if(recd_dtmf == "1"): # Play main menu again
            playSound("audio/builtin/menu.mp3")

        elif(recd_dtmf == "2"): # Get TTS Weather data
            try:
                w = getWeather(OWM_WEATHER_CITY_NAME)
                spokenString = "The time is " + theTime + ". "
                spokenString += "Weather " + w.detailed_status + ". Temp " + str(int(w.temperature('fahrenheit').get("temp"))) + " degrees. "
                spokenString += "Wind " + str(int(w.wind().get("speed") * 1.944)) + " knots. Humidity " + str(w.humidity) + " percent."
                speak(spokenString)
            except:
                playSound("audio/builtin/error.mp3")

        elif(recd_dtmf == "3"): # Get Live SSTV
            try:
                getSSTV()
                playSound("audio/cache/cache.wav")
            except:
                playSound("audio/builtin/error.mp3")

################################################################ VOICEMAIL APPLICATION
        elif(recd_dtmf == "4"): # Voice Mail
            playSound("audio/builtin/voicemail/menu.mp3")
            playSound("audio/builtin/ack.wav")
            userOption = wait_for_DTMF()
            sleep(1) # Wait for transmission to end
            if(userOption == "1"): # Existing User Login
                playSound("audio/builtin/voicemail/loginphone.mp3")
                userPhone = getVerifiedInput(10) # Get user's phone number
                userPhone = "".join(userPhone.split()) # Format
                userAlreadyExists = False
                with open("db/voicemail/users.db", "r") as f: # Scan DB for number
                    for i in f.readlines():
                        if(i.split("@")[0] == userPhone):
                            userAlreadyExists = True
                
                # If found run 2FA and login
                if(userAlreadyExists):
                    userEntry = i.strip("\n")
                    userTFACode = ""
                    for n in range(4):
                        userTFACode += str(random.randint(0,9)) # Generate and email 2FA code
                    sendMail(userEntry, "AcuityWS 2FA", "2FA code to log in to voicemail: " + userTFACode)
                    playSound("audio/builtin/voicemail/loginTFA.mp3")
                    recTFA = getVerifiedInput(4) # Get code from user
                    if("".join(recTFA.split()) == userTFACode): # Verify 2FA
                        while(True):
                            # Logged-in Voicemail menu
                            playSound("audio/builtin/voicemail/loggedinmenu.mp3")
                            playSound("audio/builtin/ack.wav")
                            userLoggedInOption = wait_for_DTMF() # Get user menu choice
                            sleep(1)
                            if(userLoggedInOption == "1"): # Play received messages
                                voiceMails = os.listdir("db/voicemail/messages")
                                for i in voiceMails:
                                    recipient = i.split(" ")[0]
                                    sender = i.split(" ")[1].strip(".wav")
                                    if(recipient == userPhone):
                                        speak("Message from " + " ".join(sender.split()) + ".")
                                        playSound("db/voicemail/messages/" + i)
                                        sleep(1)
                                        os.remove("db/voicemail/messages/" + i)
                                playSound("audio/builtin/voicemail/nonewmsgs.mp3")

                            elif(userLoggedInOption == "2"): # Send a message
                                playSound("audio/builtin/voicemail/sendprompt.mp3")
                                recipientNumber = getVerifiedInput(10)
                                recipientNumber = "".join(recipientNumber.split())
                                with open("db/voicemail/users.db", "r") as f:
                                    for i in f.readlines():
                                        if(i.split("@")[0] == recipientNumber):
                                            playSound("audio/builtin/voicemail/recording.mp3")
                                            playSound("audio/builtin/ack.wav")
                                            sleep(1)
                                            recordAudio("db/voicemail/messages/" + recipientNumber + " " + userPhone + ".wav", 30)
                                            sendMail(i, "AcuityWS Voicemail", "You have just received a voice message from " + userPhone)
                                            playSound("audio/builtin/ack.wav")
                            else: # Log out
                                break
                    else: # If 2FA codes do not match:
                        playSound("audio/builtin/voicemail/tfainvalid.mp3")
                else: # If account login is not found:
                    playSound("audio/builtin/voicemail/doesnotexist.mp3")

            elif(userOption == "2"): # New User Sign Up
                playSound("audio/builtin/voicemail/signinprompt.mp3")
                userPhone = getVerifiedInput(10) # Get phone
                playSound("audio/builtin/voicemail/carrierprompt.mp3")
                playSound("audio/builtin/ack.wav")
                userCarrierID = wait_for_DTMF() # Get carrier
                sleep(1)
                userCarrierString = SMS_GATEWAYS.get(userCarrierID)
                userEntry = "".join(userPhone.split()) + userCarrierString + "\n" # Generate DB entry (contact email)
                userAlreadyExists = False
                with open("db/voicemail/users.db", "r") as f: # If already exists notify and stop
                    for i in f.readlines():
                        if(i.strip("\n") == userEntry):
                            userAlreadyExists = True
                            playSound("audio/builtin/voicemail/alreadyexists.mp3")
                if(not userAlreadyExists): # If user doesn't exist run 2FA
                    userTFACode = ""
                    for n in range(4):
                        userTFACode += str(random.randint(0,9))
                    sendMail(userEntry, "AcuityWS 2FA", "2FA code to set up voicemail: " + userTFACode)
                    playSound("audio/builtin/voicemail/loginTFA.mp3")
                    recTFA = getVerifiedInput(4)
                    if("".join(recTFA.split()) == userTFACode): # If 2FA matches add to DB
                        with open("db/voicemail/users.db", "a") as f:
                            f.write(userEntry)
                            playSound("audio/builtin/voicemail/accountcreated.mp3")
                    else: # If 2FA codes do not match
                        playSound("audio/builtin/voicemail/tfainvalid.mp3")

            elif(userOption == "3"): # Existing User Close Account
                playSound("audio/builtin/voicemail/loginphone.mp3")
                userPhone = getVerifiedInput(10) # Get phone
                userPhone = "".join(userPhone.split())
                userAlreadyExists = False
                with open("db/voicemail/users.db", "r") as f: 
                    for i in f.readlines():         
                        if(i.split("@")[0] == userPhone): 
                            userAlreadyExists = True
                            userEntry = i.strip("\n") # Get DB entry for 2FA
                if(userAlreadyExists): # If acct exists, continue
                    userTFACode = ""
                    for n in range(4):
                        userTFACode += str(random.randint(0,9))
                    sendMail(userEntry, "AcuityWS 2FA", "2FA code to confirm account closure: " + userTFACode)
                    playSound("audio/builtin/voicemail/loginTFA.mp3")
                    recTFA = getVerifiedInput(4)
                    if("".join(recTFA.split()) == userTFACode): # If 2FA matches delete account
                        with open("db/voicemail/users.db", "r") as f: # Read DB
                            dbContents = f.readlines()
                            dbContents.remove(userEntry) # Delete account from DB in memory
                        with open("db/voicemail/users.db", "w") as f: # Write new DB
                            f.writelines(dbContents)

                        voiceMails = os.listdir("db/voicemail/messages")  # Cleanup unread voicemail
                        for i in voiceMails:
                            recipient = i.split(" ")[0]
                            sender = i.split(" ")[1].strip(".wav")
                            if(recipient == userPhone): 
                                os.remove("db/voicemail/messages/" + i)

                        playSound("audio/builtin/voicemail/accountclosure.mp3")
                    else: # If 2FA codes do not match
                        playSound("audio/builtin/voicemail/tfainvalid.mp3")
                else: # If account doesn't exist
                    playSound("audio/builtin/voicemail/doesnotexist.mp3")
################################################################ END VOICEMAIL APPLICATION

        elif(recd_dtmf == "*"): # SFX Easter Egg :)
            playSound("audio/builtin/singledigitprompt.mp3")
            playSound("audio/builtin/ack.wav")
            userOption = wait_for_DTMF()
            sleep(1)
            if(userOption == "1"):
                playSound("audio/builtin/sfx/1.mp3")
            elif(userOption == "2"):
                playSound("audio/builtin/sfx/2.mp3")
            elif(userOption == "3"):
                playSound("audio/builtin/sfx/3.mp3")
            else:
                playSound("audio/builtin/sfx/4.mp3")
        
        elif(recd_dtmf == "#"): # More Information + input help
            playSound("audio/builtin/moreinfo.mp3")
            playSound("audio/builtin/inputhelp.mp3")

        else: # Default to menu (1)
            playSound("audio/builtin/menu.mp3")

        # At the end of every transmission:
        playSound("audio/builtin/end.wav")
        sleep(5) # Transmission cooldown
    
    # We want the station to be up at all times, so if a fatal error happens, log it and restart.
    except Exception as e:
        now = datetime.now()
        print("[FATAL] Server encountered a fatal exception at " + now.strftime('%Y-%m-%d %H:%M:%S') + ": " + str(e) + ". Relaunching...")
        crash_restart = True
        sleep(1) # prevent overload due to error looping
