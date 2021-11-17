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
import smtplib
from email.mime.text import MIMEText
import random
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
SMTP_EMAIL_ADDRESS = confLines[3]
SMTP_EMAIL_PASSWORD = confLines[4]
SMTP_SERVER_ADDRESS = confLines[5]
SMTP_SERVER_PORT = int(confLines[6])

################################################################ PROGRAM CONSTANTS (Should not need to be modified)
FORMAT = pyaudio.paInt16
CHANNELS = 1
SAMPLE_RATE = 12000
INPUT_BLOCK_TIME = 0.1
INPUT_FRAMES_PER_BLOCK = int(SAMPLE_RATE*INPUT_BLOCK_TIME)
DTMF_FREQ_TOLERANCE = 5
FFT_NOISE_REJECTION = 20
DTMF_RPT_DELAY = 0.3
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
    'A': [1633, 697],
    'B': [1633, 770],
    'C': [1633, 852],
    'D': [1633, 941],
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
CLIPS = {
    # General (beeps, menus, errors)
    "ack" : "audio/builtin/ack.wav",                                     # Acknowledgement beep
    "end" : "audio/builtin/end.wav",                                     # End transmission beep
    "mainMenu" : "audio/builtin/menu.mp3",                               # Main menu
    "moreInfo" : "audio/builtin/moreinfo.mp3",                           # More information about the station
    "inputConf" : "audio/builtin/inputconf.mp3",                         # Input confirmation
    "crash" : "audio/builtin/crash.mp3",                                 # Server crash warning
    "apiError" : "audio/builtin/error.mp3",                              # Non-fatal error warning
    "singleDigitPrompt" : "audio/builtin/singledigitprompt.mp3",         # Prompt the user for a single digit
    "loginTFA" : "audio/builtin/voicemail/loginTFA.mp3",                 # Prompt user for two-factor auth code.
    "invalidTFA" : "audio/builtin/voicemail/tfainvalid.mp3",             # If user's TFA code is invalid.
    # Voicemail Applet
    "vmMenu" : "audio/builtin/voicemail/menu.mp3",                       # Voicemail main menu
    "vmLoginPhonePrompt" : "audio/builtin/voicemail/loginphone.mp3",     # Enter phone number to login
    "vmLoggedInMenu" : "audio/builtin/voicemail/loggedinmenu.mp3",       # Voicemail logged-in actions menu
    "vmSendPrompt" : "audio/builtin/voicemail/sendprompt.mp3",           # Phone number to send message to
    "vmEntryNotFound" : "audio/builtin/voicemail/doesnotexist.mp3",      # If database entry is not found
    "vmSignUpPhone" : "audio/builtin/voicemail/signupprompt.mp3",        # Prompt to enter phone number to sign up
    "vmCarrierPrompt" : "audio/builtin/voicemail/carrierprompt.mp3",     # Prompt to select wireless carrier
    "vmRecording" : "audio/builtin/voicemail/recording.mp3",             # Inform user 30 second recording starts after the beep
    "vmNoNewMessages" : "audio/builtin/voicemail/nonewmsgs.mp3",         # No new messages in voice mailbox
    "vmEntryCreated" : "audio/builtin/voicemail/accountcreated.mp3",     # Account created.
    "accountClosure" : "audio/builtin/voicemail/accountclosure.mp3",     # Account closed.
    # Sound effects
    "sfx1" : "audio/builtin/sfx/1.mp3",
    "sfx2" : "audio/builtin/sfx/2.mp3",
    "sfx3" : "audio/builtin/sfx/3.mp3",
    "sfx4" : "audio/builtin/sfx/4.mp3",
    # Help
    "inputHelp" : "audio/builtin/inputHelp.mp3"
}
BANNER="""
#---------------------------------------------------#
|                    _ _      __          _______   |
|                   (_) |     \ \        / / ____|  |
|    __ _  ___ _   _ _| |_ _   \ \  /\  / / (___    |
|   / _` |/ __| | | | | __| | | \ \/  \/ / \___ \   |
|  | (_| | (__| |_| | | |_| |_| |\  /\  /  ____) |  |
|   \__,_|\___|\__,_|_|\__|\__, | \/  \/  |_____/   |
|                           __/ |                   |
|                          |___/                    |
|             Version 0.5 (Pre-release)             |
|       https://github.com/jvmeifert/acuityws       |
#---------------------------------------------------#
""" # Fancy banner!

################################################################ FUNCTIONS

################################################################ SMTP
# Send an e-mail message over SMTP
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
        log(2, "SMTP toolkit encountered an exception: " + str(e) + ".")
        return False

################################################################ AUDIO
# Record to a .wav file for a specified number of seconds.
def recordAudio(outputFilename, length): 
    pa = pyaudio.PyAudio()
    stream = pa.open(format=pyaudio.paInt16,
                    channels=1,
                    rate=SAMPLE_RATE,
                    frames_per_buffer=1024,
                    input=True)
    inFrames = []
    for i in range(0, int(SAMPLE_RATE / 1024 * int(length))):
        data = stream.read(1024)
        inFrames.append(data)
    stream.stop_stream()
    stream.close()
    pa.terminate()
    with wave.open(outputFilename, 'wb') as f:
        f.setnchannels(1)
        f.setsampwidth(pa.get_sample_size(pyaudio.paInt16))
        f.setframerate(SAMPLE_RATE)
        f.writeframes(b''.join(inFrames))

# Find if a specified frequency exists in a fourier transform array.
def fftContains(fftArr, freq): 
    for i in range(freq - DTMF_FREQ_TOLERANCE, freq + DTMF_FREQ_TOLERANCE):
        return (i in fftArr)

# Wait for and return the character represented by a DTMF tone, or return "" if timed out.
def wait_for_DTMF(timeout = -1): 
    pa = pyaudio.PyAudio() # Open stream on PortAudio
    stream = pa.open(format=FORMAT, channels=CHANNELS,
            rate=SAMPLE_RATE, input=True,
            frames_per_buffer=INPUT_FRAMES_PER_BLOCK)

    stream.read(INPUT_FRAMES_PER_BLOCK) # Flush buffer

    listenerDuration = 0
    while (True):
        expFrames = [] # Frames represented by integers
        chunkFFT = [] # Fast Fourier Transform of the specified chunk
        listenerDuration += 1
        if(listenerDuration > timeout and timeout > 0): # Listener timeout
            stream.stop_stream()
            stream.close()
            pa.terminate()
            return ""

        # Record next chunk of audio
        frames = stream.read(INPUT_FRAMES_PER_BLOCK)

        # Format audio for FFT
        frameIter = 0
        while(frameIter < len(frames) - 1): 
            sFrame = frames[frameIter:frameIter+2]
            expFrames.append(struct.unpack("<h", sFrame)[0])
            frameIter += 2
        
        # Apply FFT to formatted array
        chunkFFT = np.fft.fft(expFrames, SAMPLE_RATE)

        # Convert FFT to real integers
        for i in range(len(chunkFFT)):
            chunkFFT[i] = int(np.absolute(chunkFFT[i]))
        
        # Calculate noise threshold
        noiseThreshold = FFT_NOISE_REJECTION * np.average(chunkFFT) 

        denoisedFreqs = []
        for i in range(len(chunkFFT)): # Denoise FFT array
            if (chunkFFT[i] > noiseThreshold):
                denoisedFreqs.append(i)

        # Analyze freqs for pairs and return represented chars
        for dtmfChar, dtmfPair in DTMF_FREQS.items(): 
            if (fftContains(denoisedFreqs, dtmfPair[0]) and 
                fftContains(denoisedFreqs, dtmfPair[1])):
                stream.stop_stream()
                stream.close()
                pa.terminate() # Close pyAudio instance
                return dtmfChar

# Speak a line on the default audio device with gTTS
def speak(text): 
    tts = gTTS(text=text, lang='en')
    tts.save("audio/cache/cache.mp3")
    playSound("audio/cache/cache.mp3")

# Play a sound on the default audio device
def playSound(filename): 
    p = vlc.MediaPlayer(filename)
    p.play()
    with audioread.audio_open(filename) as f:
        sleep(f.duration + 1)

# Get DTMF input of a specified length
def getDTMFinput(length): 
    output = ""
    for i in range(length):
        output += wait_for_DTMF()
        sleep(DTMF_RPT_DELAY)
    sleep(1 - DTMF_RPT_DELAY)
    playSound(CLIPS.get("ack"))
    return output

# Get and confirm DTMF input of a specified length
def getVerifiedInput(length): 
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
# Get the weather observation from OWM at a specified location
def getWeatherAtCity(place): 
    owm = OWM(OPENWEATHERMAP_API_KEY)
    mgr = owm.weather_manager()
    observation = mgr.weather_at_place(place)
    return observation.weather

def getWeatherAtCoords(lat,lon):
    owm = OWM(OPENWEATHERMAP_API_KEY)
    mgr = owm.weather_manager()
    observation = mgr.weather_at_coords(lat,lon)
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
def getDateAndTime(): 
        now = datetime.now()
        return now.strftime('%Y-%m-%d %H:%M:%S')
# Short time only
def getTime():
        now = datetime.now()
        return now.strftime("%H:%M")

################################################################ VOICEMAIL TOOLKIT
# Find if an entry exists in the user database
def entryExists(userEntry): 
    with open("db/voicemail/users.db", "r") as f:
        for i in f.readlines():
            if(i.strip("\n") == userEntry):
                return True
        return False # if not found

# Find if a phone number exists in the user database
def phoneExists(userPhone):
    with open("db/voicemail/users.db", "r") as f:
        for i in f.readlines():
            if(i.split("@")[0] == userPhone):
                return True
        return False # if not found

# Verify a login with two-factor authentication
def verifyTFA(userEntry): 
    userTFACode = ""
    for n in range(4):
        userTFACode += str(random.randint(0,9))
    sendMail(userEntry, "AcuityWS", "Here's your 2FA code: " + userTFACode)
    playSound(CLIPS.get("loginTFA"))
    recTFA = getVerifiedInput(4)
    if("".join(recTFA.split()) == userTFACode):
        return True
    else:
        return False # if 2fa code not valid

# Get a user's database entry from their phone number
def getEntry(userPhone):
    with open("db/voicemail/users.db", "r") as f:
        for i in f.readlines():
            if(i.split("@")[0] == userPhone):
                return i.strip("\n")
        return False # if no matching entry found

# Send a 30-second voice message.
def sendVoicemail(recipientNumber, userPhone): 
    with open("db/voicemail/users.db", "r") as f:
        for i in f.readlines():
            if(i.split("@")[0] == recipientNumber):
                playSound(CLIPS.get("vmRecording"))
                playSound(CLIPS.get("ack"))
                sleep(1)
                recordAudio("db/voicemail/messages/" + recipientNumber + " " + userPhone + ".wav", 30)
                sendMail(i, "AcuityWS", "You have just received a voice message from " + userPhone + ".")
                playSound(CLIPS.get("ack"))

# Read off a user's voicemail
def readVoicemail(userPhone):
    voiceMails = os.listdir("db/voicemail/messages")
    for i in voiceMails:
        recipient = i.split(" ")[0]
        sender = i.split(" ")[1].strip(".wav")
        if(recipient == userPhone):
            speak("Message from " + " ".join(list(sender)) + ".")
            playSound("db/voicemail/messages/" + i)
            sleep(1)
            os.remove("db/voicemail/messages/" + i)
    playSound(CLIPS.get("vmNoNewMessages"))

################################################################ LOGGING
# Log should be initialized every time the program is started.
def initLog():
    try:
        os.remove("logs/acuityWS.log")
    except:
        print("(Log init) No previous log file exists. Creating one now.")
    with open("logs/acuityWS.log", "w") as f:
        f.write(getDateAndTime() + " [INFO]  Logging initialized.\n")
        print(getDateAndTime() + " [INFO]  Logging initialized.")

# Log an event.
def log(level, data):
    output = getDateAndTime() + " "
    if(level == 0):
        output += "[INFO]  "
    elif(level == 1):
        output += "[WARN]  "
    elif(level == 2):
        output += "[ERROR] "
    else:
        output += "[FATAL] "
    output += data
    with open("logs/acuityws.log", "a") as f:
        f.write(output + "\n")
    print(output)
################################################################ END FUNCTIONS

################################################################ MAIN LOOP
print(BANNER) # Sign-of-life
initLog() # Initialize log
clean_start = True # Indicate this is a clean start
while(True):
    try:
        # Notify listeners if a crash happens
        if(not clean_start): 
            playSound(CLIPS.get("crash"))
            clean_start = True

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
                w = getWeatherAtCity(OWM_WEATHER_CITY_NAME)
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
                log(0, "Retrieved live SSTV.")
                playSound("audio/cache/cache.wav")
            except Exception as e:
                log(2, "SSTV applet encountered an exception: " + str(e) + ".")
                playSound(CLIPS.get("apiError"))

################################################################ VOICEMAIL APPLICATION
        elif(recd_dtmf == "4"): # Voice Mail
            log(0, "Voicemail applet started.")
            playSound(CLIPS.get("vmMenu"))
            playSound(CLIPS.get("ack"))
            userOption = wait_for_DTMF()
            sleep(1) # Wait for transmission to end
            if(userOption == "1"): # Existing User Login
                playSound(CLIPS.get("vmLoginPhonePrompt"))
                userPhone = getVerifiedInput(10) # Get user's phone number
                log(0, "User " + userPhone + " is logging in.")
                # If found run 2FA and login
                if(phoneExists(userPhone)):
                    userEntry = getEntry(userPhone)
                    if(verifyTFA(userEntry)): # Verify 2FA
                        log(0, "User " + userPhone + " logged in.")
                        while(True):
                            # Logged-in menu
                            playSound(CLIPS.get("vmLoggedInMenu"))
                            playSound(CLIPS.get("ack"))
                            userLoggedInOption = wait_for_DTMF() # Get user menu choice
                            sleep(1)
                            if(userLoggedInOption == "1"): # Play received messages
                                log(0, "User " + userPhone + " played received messages.")
                                readVoicemail(userPhone)
                            elif(userLoggedInOption == "2"): # Send a message
                                playSound(CLIPS.get("vmSendPrompt"))
                                recipientNumber = getVerifiedInput(10)
                                log(0, "User " + userPhone + " sent a message to user " + recipientNumber + ".")
                                sendVoicemail(recipientNumber, userPhone)
                            else: # Log out
                                break
                    else: # If 2FA codes do not match
                        log(1, "User " + userPhone + " failed two-factor authentication.")
                        playSound(CLIPS.get("invalidTFA"))
                else: # If account login is not found:
                    log(1, "User " + userPhone + " attempted to log into an account that does not exist.")
                    playSound(CLIPS.get("vmEntryNotFound"))

            elif(userOption == "2"): # New User Sign Up
                playSound(CLIPS.get("vmSignUpPhone"))
                userPhone = getVerifiedInput(10) # Get phone
                log(0, "User (NEW) " + userPhone + " is signing up.")
                playSound(CLIPS.get("vmCarrierPrompt"))
                playSound(CLIPS.get("ack"))
                userCarrierID = wait_for_DTMF() # Get carrier
                sleep(1)
                userCarrierString = SMS_GATEWAYS.get(userCarrierID)
                userEntry = userPhone + userCarrierString # Generate DB entry (contact email)
                if(not entryExists(userEntry)): # If user doesn't exist run 2FA
                    if(verifyTFA(userEntry)):
                        with open("db/voicemail/users.db", "a") as f: # Create entry for user
                            log(0, "User " + userPhone + "'s account has been created.")
                            f.write(userEntry + "\n")
                            playSound(CLIPS.get("vmEntryCreated"))
                    else: # If 2FA codes do not match
                        log(1, "User " + userPhone + " failed two-factor authentication.")
                        playSound(CLIPS.get("invalidTFA"))
                else:
                    log(1, "User " + userPhone + "'s account already exists.")
                    playSound(CLIPS.get("vmEntryAlreadyExists"))

            elif(userOption == "3"): # Existing User Close Account
                playSound(CLIPS.get("vmLoginPhonePrompt"))
                userPhone = getVerifiedInput(10) # Get phone
                log(0, "User " + userPhone + " is closing their account.")
                if(phoneExists(userPhone)): # If acct exists, continue
                    userEntry = getEntry(userPhone)
                    if(verifyTFA(userEntry)): # If 2FA matches delete account
                        with open("db/voicemail/users.db", "r") as f: # Read DB
                            dbContents = f.readlines()
                            dbContents.remove(userEntry + "\n") # Delete account from DB in memory
                        with open("db/voicemail/users.db", "w") as f: # Write new DB
                            f.writelines(dbContents)

                        voiceMails = os.listdir("db/voicemail/messages")  # Cleanup unread voicemail
                        for i in voiceMails:
                            recipient = i.split(" ")[0]
                            sender = i.split(" ")[1].strip(".wav")
                            if(recipient == userPhone): 
                                os.remove("db/voicemail/messages/" + i)
                        log(0, "User " + userPhone + " has closed their account.")
                        playSound(CLIPS.get("accountClosure"))
                    else: # If 2FA codes do not match
                        log(1, "User " + userPhone + " failed two-factor authentication.")
                        playSound(CLIPS.get("invalidTFA"))
                else: # If account doesn't exist
                    log(1, "User " + userPhone + " does not exist and cannot be removed.")
                    playSound(CLIPS.get("vmEntryNotFound"))

################################################################ MENU CHOICES CONTINUED
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

        elif(recd_dtmf == "0"): # Help
            log(0, "Playing help.")
            playSound(CLIPS.get("help"))
        
        else: # Default to menu (1)
            log(1, "User choice " + recd_dtmf + " is invalid. Defaulting to main menu.")
            playSound(CLIPS.get("mainMenu"))

        # At the end of every transmission:
        playSound(CLIPS.get("end"))
        log(0, "Transmission ended.")
        sleep(3) # Transmission cooldown

################################################################ END MENU OPTIONS
    # We want the station to be up at all times, so if a fatal error happens, log it and restart.
    except Exception as e:
        log(3,"AcuityWS encountered a fatal exception: " + str(e) + "! Restarting...")
        clean_start = False
        sleep(1) # prevent overload due to error looping
