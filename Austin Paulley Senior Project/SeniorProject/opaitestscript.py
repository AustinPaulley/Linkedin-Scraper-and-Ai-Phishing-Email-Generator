import openai

# Function to test OpenAI API
def test_openai():
    openai.api_key = input("Enter your OpenAI API key: ")

    prompt = "Write a short story about a robot learning to cook."

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=100
        )
        print("Generated text:", response['choices'][0]['message']['content'])

    except Exception as e:
        print(f"Error during OpenAI completion: {e}")

if __name__ == "__main__":
    test_openai()
