import pyttsx3

def list_voices():
    engine = pyttsx3.init()
    voices = engine.getProperty('voices')
    print(f"Found {len(voices)} voices:")
    for index, voice in enumerate(voices):
        print(f"Voice {index}:")
        print(f" - ID: {voice.id}")
        print(f" - Name: {voice.name}")
        print(f" - Languages: {voice.languages}")
        print(f" - Gender: {voice.gender}")
        print(f" - Age: {voice.age}")
        print("-" * 20)

if __name__ == "__main__":
    try:
        list_voices()
    except Exception as e:
        print(f"Error listing voices: {e}")
