from gtts import gTTS

def speak(text):
    tts = gTTS(text=text, lang='en')
    tts.save("output.mp3")
speak(input("Text to TTS:"))