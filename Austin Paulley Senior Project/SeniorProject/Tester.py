import os
import tkinter as tk
from tkinter import ttk, filedialog
from tkinter.scrolledtext import ScrolledText
from tkinter import messagebox
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import openai
from pymongo import MongoClient
import json
import threading
import logging
import datetime
import re


mongo_uri = ""
openai.api_key = ""

def update_user_dropdown():
    """Fetch user names from MongoDB and update the dropdown options."""
    client = MongoClient(mongo_uri)
    db = client['mydatabase']
    collection = db['profiles']
    
    # Fetch user names from the database
    user_names = [user['name'] for user in collection.find({}, {'name': 1, '_id': 0})]
    
    # Update the dropdown with user names
    user_dropdown['values'] = user_names

def on_user_selected(event):
    """Handle the selection of a user from the dropdown."""
    selected_user = user_dropdown.get()
    if selected_user:
        search_user(selected_user)  # Call the existing function to pull user data

def search_user(user_name):
    # Connect to MongoDB and check if the user exists
    client = MongoClient(mongo_uri)
    db = client['mydatabase']
    collection = db['profiles']

    # Find the user by name in MongoDB
    user_data = collection.find_one({"name": {"$regex": f"^{user_name}$", "$options": 'i'}})

    if user_data:
        print(f"User {user_name} found in the database.")
        display_user_data(user_data)  # Display user data from the database
        return user_data
    else:
        print(f"User {user_name} not found in the database. Please provide a LinkedIn URL to scrape.")
        messagebox.showinfo("User Not Found", f"User '{user_name}' not found. Add them using a LinkedIn URL.")
        return None

def display_user_data(user_data):
    # Display the fetched data from MongoDB (this can be adjusted as needed for the UI)
    email_display.insert(tk.END, f"\nUser Profile: {user_data}")
    email_display.see(tk.END)

def add_new_user(linkedin_url, progress_var, progress_label):
    # Connect to MongoDB and check if the user already exists by URL
    client = MongoClient(mongo_uri)
    db = client['mydatabase']
    collection = db['profiles']

    # Check if the user with this LinkedIn URL already exists
    if linkedin_url:  # Only check for URL if it's provided
        existing_user = collection.find_one({"url": linkedin_url})

        if existing_user:
            print(f"User with LinkedIn URL {linkedin_url} already exists in the database.")
            messagebox.showinfo("User Exists", f"User with LinkedIn URL already exists in the database.")
            return existing_user  # Return the existing user's data from MongoDB
        else:
            print(f"User with LinkedIn URL {linkedin_url} not found. Proceeding to scrape.")
            return scrape_linkedin_profile(linkedin_url, progress_var, progress_label)  # Only scrape if not found
    else:
        print(f"LinkedIn URL is empty. Skipping scraping.")
        progress_label.config(text="No LinkedIn URL provided for scraping.")
        return None
    
def scrape_linkedin_profile(url, progress_var, progress_label, headless=True):
    try:
        options = Options()
        options.headless = headless
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        print(f"Starting LinkedIn scraping for URL: {url}")
        progress_var.set(10)
        progress_label.config(text="Starting LinkedIn Scraping...")
        driver = webdriver.Chrome(options=options)
        print("Chrome WebDriver initialized.")
        driver.get(url)
        print(f"Opened URL: {url}")
        progress_var.set(30)
        progress_label.config(text="Loading LinkedIn Page...")

        # Check for security measures or sign-in prompts
        if "security" in driver.title.lower() or "sign in" in driver.title.lower():
            print(f"Security page detected or Sign-in required for URL: {url}")
            input("Please manually sign in or bypass security. Press Enter to continue...")
        progress_var.set(50)
        progress_label.config(text="Extracting Data...")
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            print("Page scrolled to bottom.")
        except Exception as js_error:
            print(f"JavaScript error during scroll: {js_error}")
            driver.quit()
            return None
        html = driver.page_source
        print("Page source retrieved.")
        driver.quit()
        progress_var.set(70)
        progress_label.config(text="Processing Data...")
        soup = BeautifulSoup(html, 'html.parser')
        print("HTML parsed with BeautifulSoup.")

        # Extract JSON data from script tag
        script = soup.find('script', {'type': 'application/ld+json'})
        if script is not None:
            print("Found JSON script in page source.")
            data = json.loads(script.text)
            person = [x for x in data.get('@graph', []) if x.get('@type') == 'Person'][0]
            print(f"Person data found: {person}")
            profile_data = {
                'name': person.get('name', ''),
                'job_title': person.get('jobTitle', ''),
                'current_company_name': [org.get('name', '') for org in person.get('worksFor', [])],
                'location': person.get('address', {}).get('addressLocality', ''),
                'education': ', '.join([edu.get('name', '') for edu in person.get('alumniOf', []) if edu.get('@type') == 'EducationalOrganization']),
                'previous_jobs': ', '.join([org.get('name', '') for org in person.get('alumniOf', []) if org.get('@type') == 'Organization']),
                'about': soup.find('meta', {'name': 'description'})['content'] if soup.find('meta', {'name': 'description'}) else '',
                'url': url
            }
            print(f"Profile data extracted: {profile_data}")

            # MongoDB operations
            print("Connecting to MongoDB...")
            client = MongoClient(mongo_uri)
            db = client['mydatabase']
            collection = db['profiles']
            collection.insert_one(profile_data)
            print("Profile data saved to MongoDB.")
            progress_var.set(100)
            progress_label.config(text="LinkedIn Scraping Complete")
            return profile_data
        else:
            print("JSON script not found on page.")
            progress_var.set(0)
            progress_label.config(text="Failed to scrape data.")
            return None
    except Exception as e:
        print(f"Exception occurred: {e}")
        logging.error(f"Error in scraping LinkedIn profile: {e}")
        progress_var.set(0)
        progress_label.config(text="Error during LinkedIn Scraping.")
        return None

def construct_prompt(profile_data, option):
    try:
        # Original prompt to invite someone to an event
        prompt = f"Write an email to {profile_data.get('name', 'the person')} inviting them to attend a job fair event from ABCC College or Alabama Berkley Community College. The location and time is to be announced and will be found on ABCCEvents.net. The email should come from Tom Timothy, Dean at the school, and direct the person to the website for event information."
        
        # Add specific details based on the selected option
        if option == "1":
            prompt += f"\nHere's some additional information: \n"
            prompt += f"Job Title: {profile_data.get('job_title', '')}\n"
            prompt += f"Current Company: {', '.join(profile_data.get('current_company_name', []))}\n"
            prompt += f"Location: {profile_data.get('location', '')}\n"
            prompt += f"Education: {profile_data.get('education', '')}\n"
            prompt += f"Previous Jobs: {profile_data.get('previous_jobs', '')}\n"
            prompt += f"About: {profile_data.get('about', '')}\n"
        
        elif option == "2":
            prompt += f"\nHere's some job-related information: \n"
            prompt += f"Job Title: {profile_data.get('job_title', '')}\n"
            prompt += f"Current Company: {', '.join(profile_data.get('current_company_name', []))}\n"
            prompt += f"Previous Jobs: {profile_data.get('previous_jobs', '')}\n"
        
        elif option == "3":
            prompt += f"\nHere's some education-related information: \n"
            prompt += f"Education: {profile_data.get('education', '')}\n"
            prompt += f"About: {profile_data.get('about', '')}\n"
        
        print(f"Prompt constructed successfully: {prompt}")
        return prompt

    except Exception as e:
        print(f"Error during prompt construction: {e}")
        logging.error(f"Error in constructing prompt: {e}")
        return None

def on_generate_clicked(url_entry, option_combobox, temperature_slider, model_combobox, progress_var, progress_label, test_model_combobox):
    # Find user in MongoDB
    user_name = search_entry.get()
    client = MongoClient(mongo_uri)
    db = client['mydatabase']
    collection = db['profiles']
    user_data = collection.find_one({"name": {"$regex": f"^{user_name}$", "$options": 'i'}})

    if user_data:
        print(f"User {user_name} found in the database. Using existing data.")
        # Start the email chain generation directly
        chain_count = 1  # Set to 1 for a single email, or modify this to prompt user
        generate_email_chain(user_data, option_combobox.get()[0], float(temperature_slider.get()), 
                             model_combobox.get(), chain_count, progress_var, progress_label)
    else:
        print("User not found in the database.")
        progress_label.config(text="User not found in the database.")

def generate_email_from_data(user_data, option, temperature, model, progress_var, progress_label):
    # Construct and send a prompt to OpenAI
    prompt = construct_prompt(user_data, option)
    print(f"Using existing data to construct prompt: {prompt}")
    try:
        progress_var.set(60)
        progress_label.config(text="Generating Email...")
        response = openai.ChatCompletion.create(
            model=model,
            messages=[{"role": "system", "content": "You are a helpful assistant."},
                      {"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=1000
        )
        email_content = response['choices'][0]['message']['content']
        print(f"Generated Email Content: {email_content}")
        progress_var.set(100)
        progress_label.config(text="Email Generation Complete")
        return email_content

    except Exception as openai_error:
        print(f"Error during OpenAI completion: {openai_error}")
        progress_label.config(text="Error during Email Generation.")
        return None

def generate_email_chain(user_data, option, temperature, model, chain_count, progress_var, progress_label, selected_test_model):
    global stop_email_generation

    for i in range(chain_count):  # Repeat for each group
        if stop_email_generation:
            print(f"Email generation stopped at group {i+1}.")
            break

        print(f"Generating email group {i+1}/{chain_count}...")
        primary_email_content = generate_email_from_data(user_data, option, temperature, model, progress_var, progress_label)
        
        if not primary_email_content:
            print("Primary email generation failed.")
            break

        email_group = [{"type": "primary", "content": primary_email_content}]

        # Generate responses for the primary email
        response_count = email_chain_size_slider.get()
        for j in range(response_count):
            if stop_email_generation:
                print("Email generation stopped during responses.")
                break

            print(f"Generating response email {j+1} for group {i+1}...")
            response_email = generate_response_email(primary_email_content, user_data, temperature, model, j+1)
            if not response_email:
                print(f"Failed to generate response email {j+1} for group {i+1}.")
                break

            email_group.append({"type": f"response_{j+1}", "content": response_email})

        # Test legitimacy for the entire group
        group_legitimacy_result = evaluate_chain_legitimacy(email_group, selected_test_model)
        group_legitimacy_score = group_legitimacy_result["score"]
        print(f"Group {i+1} Legitimacy Score: {group_legitimacy_score}%")

        # Store the email group in MongoDB
        store_chain_results(
            name=user_data['name'],
            temperature=temperature,
            response_count=len(email_group) - 1,  # Exclude the primary email
            legitimacy_result=group_legitimacy_result,
            email_chain=email_group,
            generating_ai=model,
            testing_ai=selected_test_model
        )

        # Display results for the group
        email_display.insert(tk.END, f"\nEmail Group {i+1}:\n")
        for email in email_group:
            email_display.insert(tk.END, f"{email['type'].capitalize()}:\n{email['content']}\n")
        email_display.insert(tk.END, f"Legitimacy Score: {group_legitimacy_score}%\n{'-'*50}\n")

        progress_var.set(((i + 1) * 100) / chain_count)
        progress_label.config(text=f"Progress: {i+1}/{chain_count} email groups generated.")

    progress_label.config(text="Email Generation Complete")
    print("Email generation and testing complete.")

def store_chain_results(name, temperature, response_count, legitimacy_result, email_chain, generating_ai, testing_ai):
    client = MongoClient(mongo_uri)
    db = client['mydatabase']
    collection_name = f"results_chain{response_count}_temp{temperature:.1f}_gengpt_{generating_ai}_test{testing_ai}"
    results_collection = db[collection_name]

    # Log legitimacy_result for debugging
    print(f"Storing results with legitimacy_result: {legitimacy_result}")

    # Prepare the data to store
    result_data = {
        "name": name,
        "temperature": temperature,
        "response_count": response_count,
        "legitimacy_score": legitimacy_result.get('score', 0),  # Default to 0 if 'score' is missing
        "legitimacy_analysis": legitimacy_result.get('result', 'No analysis available'),  # Store full analysis
        "email_chain": email_chain,
        "generating_ai": generating_ai,
        "testing_ai": testing_ai
    }

    try:
        results_collection.insert_one(result_data)
        print(f"Data stored successfully in collection '{collection_name}'.")
    except Exception as e:
        print(f"Error storing results to MongoDB: {e}")

def generate_response_email(previous_email, user_data, temperature, model, response_number):
    """
    Generates a response email based on the previous email in the chain, simulating a group email thread.
    """
    # Simulate different senders for each response
    alternate_senders = ["John Doe", "Jane Smith", "Mark Johnson"]
    sender = alternate_senders[(response_number - 1) % len(alternate_senders)]  # Cycle through alternate senders
    
    # Generate a timestamp for the response
    timestamp = datetime.datetime.now() + datetime.timedelta(minutes=response_number * 5)  # Increment 5 mins per response
    timestamp_str = timestamp.strftime("%A, %B %d, %Y %I:%M %p")

    # Format the prompt to ask for a logical response to the previous email
    prompt = f"Respond as {sender} to the following email in an Outlook-style format:\n\n{previous_email}\n\nResponse {response_number}."

    print(f"Generating response {response_number} from {sender} to primary email.")

    try:
        response = openai.ChatCompletion.create(
            model=model,
            messages=[{"role": "system", "content": "You are a helpful assistant responding to emails in Outlook format."},
                      {"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=500
        )
        response_email_content = response['choices'][0]['message']['content']

        # Format as Outlook-style email with header
        formatted_response = (
            f"From: {sender}\n"
            f"Sent: {timestamp_str}\n"
            f"To: {user_data.get('name', 'Recipient Name')}\n"
            f"Subject: RE: Job Fair Invitation\n\n"
            f"{response_email_content}\n"
            f"--- End of Response {response_number} ---\n\n"
        )
        
        print(f"Generated Response Email {response_number}: {formatted_response}")
        return formatted_response

    except Exception as e:
        print(f"Error generating response email {response_number}: {e}")
        return None  # Return None to halt further responses if there's an error
    
def ask_email_chain_count():
    """Fetch user data when Generate Email is clicked and prepare for email generation."""
    selected_user = user_dropdown.get()  # Get the selected user from the dropdown
    if not selected_user:
        messagebox.showerror("Error", "Please select a user from the dropdown.")
        return

    # Connect to MongoDB and fetch user data
    client = MongoClient(mongo_uri)
    db = client['mydatabase']
    collection = db['profiles']
    user_data = collection.find_one({"name": {"$regex": f"^{selected_user}$", "$options": 'i'}})

    if not user_data:
        messagebox.showerror("Error", "User data not found in MongoDB.")
        return

    print(f"User {selected_user} found in the database.")
    # Open the chain count input window
    chain_window = tk.Toplevel(root)
    chain_window.title("Email Chain Count")
    chain_window.geometry("390x230")
    chain_window.configure(bg="#f8f9fa")

    # Add UI elements for chain count
    subtle_border = tk.Frame(chain_window, bg="#ced4da", bd=5, relief="solid")
    subtle_border.pack(fill="both", expand=True, padx=20, pady=20)
    content_frame = ttk.Frame(subtle_border, style="TFrame")
    content_frame.pack(padx=10, pady=10)

    # Add label and entry for chain count
    ttk.Label(content_frame, text="Enter the Number of Emails you want to generate:", font=('Helvetica', 14), background="#f8f9fa", foreground="#333333").pack(pady=10)
    chain_count_entry = tk.Entry(content_frame, font=('Helvetica', 12), relief="solid", bd=1, width=10)
    chain_count_entry.pack(pady=10)

    # Handle submission
    def submit_chain_count():
        try:
            chain_count_str = chain_count_entry.get().strip()
            if chain_count_str.isdigit():
                chain_count = int(chain_count_str)
                if chain_count > 0:
                    chain_window.destroy()
                    threading.Thread(target=generate_email_chain, args=(
                        user_data,
                        option_combobox.get()[0],
                        float(temperature_slider.get()),
                        model_combobox.get(),
                        chain_count,
                        progress_var,
                        progress_label,
                        test_model_combobox.get()
                    )).start()
                else:
                    raise ValueError("Invalid number")
            else:
                raise ValueError("Invalid number")
        except ValueError:
            messagebox.showerror("Invalid Input", "Please enter a valid number greater than 0.")
    
    submit_button = tk.Button(content_frame, text="Submit", command=submit_chain_count, bg="white", relief="solid", bd=2, highlightbackground="black", font=('Helvetica', 12))
    submit_button.pack(pady=20)
    chain_window.mainloop()

def stop_email():
    global stop_email_generation
    stop_email_generation = True
    print("Email generation process stopped by user.")

def export_email():
    print("Export email button clicked")  # Add debug print to ensure the function is called
    email_content = email_display.get("1.0", tk.END).strip()
    if not email_content:
        print("No email content to export")  # Debugging print
        messagebox.showerror("Error", "No email content to export.")
        return
    file_path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text Files", "*.txt")])
    if file_path:
        print(f"Exporting email to {file_path}")  # Debugging print
        with open(file_path, "w") as file:
            file.write(email_content)
        messagebox.showinfo("Success", f"Email content exported to {file_path}")

def update_temperature_color(value):
    value = float(value)
    red = int(min(255, max(0, 255 * (value / 2))))  # Normalize value for red (0-255)
    blue = int(min(255, max(0, 255 * (2 - value))))  # Normalize value for blue based on the range (0-2)
    temperature_slider.config(troughcolor=f'#{red:02x}00{blue:02x}')

def open_settings():
    global startup_window, mongo_uri, openai
    startup_window.withdraw()

    settings_window = tk.Toplevel()
    settings_window.title("Settings")
    settings_window.geometry("400x350")
    settings_window.configure(bg="#f8f9fa")

    subtle_border = tk.Frame(settings_window, bg="#ced4da", bd=5, relief="solid")
    subtle_border.pack(fill="both", expand=True, padx=20, pady=20)
    content_frame = ttk.Frame(subtle_border, style="TFrame")
    content_frame.pack(padx=10, pady=10)

    ttk.Label(content_frame, text="Application Settings", font=('Helvetica', 14, 'bold')).pack(pady=10)

    ttk.Label(content_frame, text="MongoDB URI:", font=('Helvetica', 12, 'bold')).pack(pady=5)
    mongo_uri_entry = ttk.Entry(content_frame, font=('Helvetica', 12), width=40)
    mongo_uri_entry.pack(pady=5)
    mongo_uri_entry.insert(0, mongo_uri or "")  # Use existing or default value

    ttk.Label(content_frame, text="OpenAI API Key:", font=('Helvetica', 12, 'bold')).pack(pady=10)
    api_key_entry = ttk.Entry(content_frame, font=('Helvetica', 12), show="*", width=40)
    api_key_entry.pack(pady=5)
    api_key_entry.insert(0, openai.api_key or "")  # Use existing or default value

    def save_and_open_main_gui():
        global mongo_uri, openai
        mongo_uri = mongo_uri_entry.get()
        openai.api_key = api_key_entry.get()

        if not mongo_uri.strip():
            messagebox.showerror("Invalid Input", "Please enter a valid MongoDB URI.")
            return
        if not openai.api_key.strip():
            messagebox.showerror("Invalid Input", "Please enter a valid API Key.")
            return

        try:
            client = MongoClient(mongo_uri)
            client.list_database_names()
            print(f"MongoDB URI saved: {mongo_uri}")
            print(f"API Key saved: {openai.api_key}")
        except Exception as e:
            messagebox.showerror("MongoDB Connection Failed", f"Error: {e}")
            return

        settings_window.destroy()
        startup_window.destroy()
        setup_gui()

    save_button = tk.Button(
        content_frame,
        text="Save and Continue",
        font=('Helvetica', 12),
        bg="white",
        fg="black",
        relief="solid",
        bd=2,
        highlightbackground="black",
        command=save_and_open_main_gui
    )
    save_button.pack(pady=20)

def clear_output():
    email_display.delete("1.0", tk.END)

def evaluate_chain_legitimacy(email_chain, selected_test_model):
    combined_content = "\n---\n".join(email["content"] for email in email_chain if "content" in email)
    
    # Advanced Prompt
    prompt = f"""
    You are an advanced email analysis assistant. Your task is to assess the legitimacy of the email chain provided based on the following criteria:

    1. **Language and Tone Consistency**: Professionalism and alignment with purpose.
    2. **Content Relevance**: Specific, actionable details relevant to the subject.
    3. **Authenticity Indicators**: Legitimate sender details, no phishing signs.
    4. **Formatting and Grammar**: Proper grammar, spelling, and structure.
    5. **Behavioral Indicators**: Absence of pressure tactics or inconsistencies.

    Provide a detailed analysis of the email chain and assign a **Legitimacy Score** (0-100). Use the format:
    - Legitimacy Score: [Your score as a number]
    - Explanation: [Your explanation]

    Email Chain:
    {combined_content}
    """
    try:
        response = openai.ChatCompletion.create(
            model=selected_test_model,
            messages=[
                {"role": "system", "content": "You are an advanced email analysis assistant."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=1000
        )
        
        result = response['choices'][0]['message']['content'].strip()
        print(f"AI Response:\n{result}")  # Debugging: Print the full response

        # Extract legitimacy score
        score_match = re.search(r"Legitimacy Score:\s*(\d+)", result, re.IGNORECASE)
        if score_match:
            score = int(score_match.group(1))
            print(f"Extracted Legitimacy Score: {score}")  # Debugging
        else:
            print("Legitimacy Score not found in AI response.")
            score = 0  # Default to 0 if the score isn't found


        return {"result": result, "score": score}
    
    except Exception as e:
        print(f"Error evaluating legitimacy: {e}")
        return {"result": None, "score": 0}

def open_single_test():
    global mongo_uri, openai
    if mongo_uri == "" or openai.api_key == "":  # Use openai.api_key instead of openai_api_key
        messagebox.showerror("Error", "MongoDB URI or OpenAI API Key is missing!")
    else:
        setup_gui()  # Proceed to the GUI if the settings are correct

def show_startup():
    global startup_window
    startup_window = tk.Tk()
    startup_window.title("LinkedIn AI Email Generator And AI Email Tester")
    startup_window.geometry("575x250")
    startup_window.configure(bg="#f8f9fa")

    # Add a border around the startup content
    subtle_border = tk.Frame(startup_window, bg="#ced4da", bd=5, relief="solid")
    subtle_border.pack(fill="both", expand=True, padx=20, pady=20)
    content_frame = ttk.Frame(subtle_border, style="TFrame")
    content_frame.pack(padx=10, pady=10)

    # Title Label
    ttk.Label(content_frame, text="LinkedIn AI Email Generator And AI Email Tester", style="TLabel", font=('Helvetica', 16, 'bold')).pack(pady=20)

    # Single Test Button (opens settings first)
    single_test_button = tk.Button(
        content_frame,
        text="Start Test",
        font=('Helvetica', 12),
        bg="white",
        fg="black",
        relief="solid",
        bd=2,
        highlightbackground="black",
        command=open_settings  # Open the settings screen when clicked
    )
    single_test_button.pack(pady=10)

    # Results Button
    results_button = tk.Button(
        content_frame,
        text="Results",
        font=('Helvetica', 12),
        bg="white",
        fg="black",
        relief="solid",
        bd=2,
        highlightbackground="black",
        command=open_results_window
    )
    results_button.pack(pady=10)

    startup_window.mainloop()

def handle_automation(url_entry, option_combobox, temperature_slider, model_combobox, progress_var, progress_label, repeat_count_entry, automate_checkbox):
    if automate_checkbox.get() == 1:  # Check if the automation checkbox is enabled
        try:
            repeat_count = int(repeat_count_entry.get())  # Get the repeat count
            if repeat_count <= 0:
                messagebox.showerror("Invalid Count", "Please enter a valid number greater than 0.")
                return
        except ValueError:
            messagebox.showerror("Invalid Input", "Please enter a valid number.")
            return
        
        # Automate email generation process
        threading.Thread(target=automated_email_generation, args=(
            url_entry.get(), option_combobox.get()[0], float(temperature_slider.get()), 
            model_combobox.get(), progress_var, progress_label, repeat_count
        )).start()
    else:
        # If automation is not enabled, just generate one email
        threading.Thread(target=generate_email, args=(
            url_entry.get(), option_combobox.get()[0], float(temperature_slider.get()), 
            model_combobox.get(), progress_var, progress_label
        )).start()

def automated_email_generation(url, option, temperature, model, progress_var, progress_label, repeat_count):
    for i in range(repeat_count):
        print(f"Generating email {i+1}/{repeat_count}...")
        
        progress_var.set((i * 100) / repeat_count)
        progress_label.config(text=f"Generating Email {i+1}/{repeat_count}...")
        
        # Call the generate_email function for each iteration
        generate_email(url, option, temperature, model, progress_var, progress_label)
        
        progress_var.set(((i + 1) * 100) / repeat_count)
        progress_label.config(text=f"Progress: {i+1}/{repeat_count} emails generated")
        email_display.insert(tk.END, f"\n--- End of Email {i+1}/{repeat_count} ---\n")
        email_display.see(tk.END)
    
    progress_label.config(text="Email Generation Complete")
    
def export_email_to_pdf(filename="emails.pdf"):
    try:
        # Initialize FPDF for PDF generation
        pdf = fpdf.FPDF(format='letter')
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        
        # Get the email content from the display area
        email_content = email_display.get(1.0, tk.END)
        
        # Split the content into lines and add each to the PDF
        lines = email_content.split('\n')
        for line in lines:
            pdf.cell(200, 10, txt=line, ln=True)
        
        # Save the PDF
        pdf.output(filename)
        print(f"Emails exported to {filename}")
        messagebox.showinfo("Success", f"Emails exported to {filename}")
    except Exception as e:
        print(f"Error exporting emails to PDF: {e}")
        messagebox.showerror("Error", f"Failed to export emails to PDF: {e}")

def open_results_window():
    global startup_window  # Ensure startup_window is recognized
    results_window = tk.Toplevel(startup_window)  # Use startup_window as the parent
    results_window.title("Results")
    results_window.geometry("800x800")  # Adjust the size as needed
    results_window.configure(bg="#f8f9fa")

    # Add a border around the results content
    subtle_border = tk.Frame(results_window, bg="#ced4da", bd=5, relief="solid")
    subtle_border.pack(fill="both", expand=True, padx=20, pady=20)
    content_frame = ttk.Frame(subtle_border, style="TFrame")
    content_frame.pack(padx=10, pady=10)

    # Title Label
    ttk.Label(content_frame, text="Retrieve Results", font=('Helvetica', 16, 'bold')).pack(pady=10)

    # MongoDB URI Input
    ttk.Label(content_frame, text="MongoDB URI:", font=('Helvetica', 12, 'bold')).pack(pady=5)
    mongo_uri_entry = ttk.Entry(content_frame, font=('Helvetica', 12), width=50)
    mongo_uri_entry.pack(pady=5)
    mongo_uri_entry.insert(0, "mongodb://localhost:27017")  # Default value (update as needed)

    # Model frame for generation and testing model selection
    model_frame = ttk.Frame(content_frame, style="TFrame")
    model_frame.pack(pady=10)

    # Generation Model Dropdown
    ttk.Label(model_frame, text="Model for Generation:", font=('Helvetica', 12, 'bold')).grid(row=0, column=0, padx=10, pady=5)
    gen_model_dropdown = ttk.Combobox(model_frame, values=["gpt-3.5-turbo", "gpt-4-turbo", "gpt-4", "gpt-4-32k"], state="readonly", font=('Helvetica', 12))
    gen_model_dropdown.grid(row=1, column=0, padx=10, pady=5)

    # Testing Model Dropdown
    ttk.Label(model_frame, text="Model for Testing:", font=('Helvetica', 12, 'bold')).grid(row=0, column=1, padx=10, pady=5)
    test_model_dropdown = ttk.Combobox(model_frame, values=["gpt-3.5-turbo", "gpt-4-turbo", "gpt-4", "gpt-4-32k"], state="readonly", font=('Helvetica', 12))
    test_model_dropdown.grid(row=1, column=1, padx=10, pady=5)

    # Temperature Slider
    ttk.Label(content_frame, text="AI Temperature Slider:", font=('Helvetica', 12, 'bold')).pack(pady=5)
    temperature_slider = tk.Scale(content_frame, from_=0.0, to=2.0, resolution=0.25, orient=tk.HORIZONTAL, length=300, bg="#f8f9fa", highlightthickness=0)
    temperature_slider.set(1)
    temperature_slider.pack(pady=10)

    # Chain Size Slider
    ttk.Label(content_frame, text="Email Chain Size:", font=('Helvetica', 12, 'bold')).pack(pady=5)
    chain_size_slider = tk.Scale(content_frame, from_=0, to=10, resolution=1, orient=tk.HORIZONTAL, length=300)
    chain_size_slider.set(0)
    chain_size_slider.pack(pady=10)

    # Retrieve Data Button
    retrieve_button = tk.Button(
        content_frame,
        text="Retrieve Data",
        font=('Helvetica', 12),
        bg="white",
        fg="black",
        relief="solid",
        bd=2,
        highlightbackground="black",
        command=lambda: fetch_results(
            results_display,
            chain_size_slider.get(),
            temperature_slider.get(),
            gen_model_dropdown.get(),
            test_model_dropdown.get(),
            mongo_uri_entry.get()  # Pass the URI dynamically
        )
    )
    retrieve_button.pack(pady=10)

    # Scrollable Text Widget for Displaying Results
    results_display = ScrolledText(content_frame, height=15, width=80, font=('Helvetica', 12), borderwidth=1, relief="solid", bg="#ffffff", fg="#333333", padx=10, pady=10)
    results_display.pack(pady=10)

def fetch_results(display_widget, chain_size, temperature, gen_model, test_model, mongo_uri):
    """Fetch test count and average legitimacy from MongoDB based on user-selected parameters."""
    try:
        # Log raw input parameters
        print(f"Inputs: chain_size={chain_size}, temperature={temperature}, gen_model={gen_model}, test_model={test_model}")

        # Construct the collection name with proper formatting
        collection_name = (
            f"results_chain{chain_size}_temp{temperature}_gengpt_{gen_model}_test{test_model}"
        )
        print(f"Constructed Collection Name: {collection_name}")  # Debugging

        # Connect to MongoDB
        client = MongoClient(mongo_uri)
        db = client['mydatabase']

        # List all available collections
        print(f"Available collections: {db.list_collection_names()}")

        # Check if the collection exists
        if collection_name in db.list_collection_names():
            collection = db[collection_name] 
            results = list(collection.find())

            # Log the number of results found
            print(f"Found {len(results)} documents in {collection_name}")

            # Count tests and calculate average legitimacy
            test_count = len(results)
            if test_count > 0:
                total_legitimacy = sum(result.get('legitimacy_score', 0) for result in results)
                average_legitimacy = total_legitimacy / test_count
            else:
                average_legitimacy = 0

            # Display results
            display_widget.delete('1.0', tk.END)
            display_widget.insert(tk.END, f"Results for:\n")
            display_widget.insert(tk.END, f"Chain Size: {chain_size}\n")
            display_widget.insert(tk.END, f"Temperature: {temperature}\n")
            display_widget.insert(tk.END, f"Generation Model: {gen_model}\n")
            display_widget.insert(tk.END, f"Testing Model: {test_model}\n\n")
            display_widget.insert(tk.END, f"Total Tests: {test_count}\n")
            display_widget.insert(tk.END, f"Average Legitimacy Score: {average_legitimacy:.2f}%\n")
        else:
            # Debug: No collection found
            print(f"Collection {collection_name} does not exist.")
            display_widget.delete('1.0', tk.END)
            display_widget.insert(tk.END, f"No data found for the selected parameters.\n")

    except Exception as e:
        display_widget.delete('1.0', tk.END)
        display_widget.insert(tk.END, f"Error fetching results: {e}")

    finally:
        # Ensure the MongoDB client connection is closed
        if 'client' in locals():
            client.close()




def setup_gui():
    global email_display, root, style, url_entry, email_chain_size_slider, option_combobox, temperature_slider, progress_var, stop_email_generation, progress_label, test_model_combobox, model_combobox, repeat_count_entry, automate_checkbox, user_dropdown

    stop_email_generation = False
    email_chain_size_slider = None 
    # Create the main window
    root = tk.Tk()
    root.title("Scraped LinkedIn AI Email Generator And AI Email Legitimacy Tester")
    root.geometry("1190x975")  # Adjust the window size as needed
    root.configure(bg="#f8f9fa")
    
    # Create a frame for the scrollbar and canvas
    main_frame = ttk.Frame(root)
    main_frame.pack(fill="both", expand=True)

    # Create a canvas widget
    canvas = tk.Canvas(main_frame, bg="#f8f9fa")
    canvas.pack(side="left", fill="both", expand=True)

    # Add a scrollbar to the canvas
    scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)
    scrollbar.pack(side="right", fill="y")

    # Configure the canvas to work with the scrollbar
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

    # Create a frame inside the canvas to hold all other widgets
    content_frame = ttk.Frame(canvas, style="TFrame")
    canvas.create_window((0, 0), window=content_frame, anchor="nw")

    # Add a subtle border around the content frame
    subtle_border = tk.Frame(content_frame, bg="#ced4da", bd=5, relief="solid")
    subtle_border.pack(fill="both", expand=True, padx=20, pady=20)

    # Define custom button styles
    style = ttk.Style()
    style.configure("TButton", font=('Helvetica', 14), background="#007bff", foreground="black", padding=10, relief="solid", bordercolor="black", bd=2)
    style.map("TButton", background=[("active", "#0056b3"), ("disabled", "#e0e0e0")], foreground=[("disabled", "#a0a0a0")])

    # Update label styles
    style.configure("TLabel", font=('Helvetica', 12, 'bold'), background="#f8f9fa", foreground="#333333")
    style.configure("TFrame", background="#f8f9fa")
    style.configure("TScale", background="#f8f9fa")
    style.configure("TEntry", background="white", foreground="black", bordercolor="black", relief="solid", bd=2)
    style.configure("TCombobox", background="white", foreground="black", bordercolor="black", relief="solid", bd=2)

    # Create a frame for the UI components inside the subtle border
    ui_frame = ttk.Frame(subtle_border, style="TFrame")
    ui_frame.pack(padx=10, pady=10)

    # User Management Section
    user_frame = ttk.Frame(ui_frame, style="TFrame")
    user_frame.pack(pady=10, fill='x')

    # Dropdown and new user input side by side
    ttk.Label(user_frame, text="Select User:", font=('Helvetica', 14, 'bold')).grid(row=0, column=0, sticky='w', padx=5, pady=5)
    user_dropdown = ttk.Combobox(user_frame, font=('Helvetica', 12), state="readonly", width=30)
    user_dropdown.grid(row=0, column=1, sticky='w', padx=5, pady=5)
    user_dropdown.bind("<<ComboboxSelected>>", on_user_selected)
    refresh_button = tk.Button(user_frame, text="Refresh User List", font=('Helvetica', 12), bg="white", fg="black", relief="solid", bd=2, highlightbackground="black", width=15, command=update_user_dropdown)
    refresh_button.grid(row=1, column=1, sticky='', padx=5, pady=5)

    # New user input field next to the dropdown
    ttk.Label(user_frame, text="Enter New User's LinkedIn URL:", font=('Helvetica', 14, 'bold')).grid(row=0, column=2, sticky='w', padx=5, pady=5)
    url_entry = ttk.Entry(user_frame, width=40, font=('Helvetica', 12))
    url_entry.grid(row=0, column=3, sticky='w', padx=5, pady=5)
    add_user_button = tk.Button(user_frame, text="Add New User", font=('Helvetica', 12), bg="white", fg="black", relief="solid", bd=2, highlightbackground="black", width=15, command=lambda: add_new_user(url_entry.get(), progress_var, progress_label))
    add_user_button.grid(row=1, column=3, sticky='', padx=5, pady=5)

    # Initial call to populate the dropdown with user names
    update_user_dropdown()
    
    separator = ttk.Separator(ui_frame, orient='horizontal')
    separator.pack(fill='x', padx=10, pady=15)

    # Data Options dropdown
    ttk.Label(ui_frame, text="Data Options:", font=('Helvetica', 14, 'bold')).pack(pady=5)
    ttk.Label(ui_frame, text="Choose the type of data you want to extract from the LinkedIn profile.", font=('Helvetica', 14), background="#f8f9fa", foreground="#666666").pack()
    option_combobox = ttk.Combobox(ui_frame, values=["1 - All Data", "2 - Job Related Info", "3 - Education Info"], style="TCombobox", state="readonly", font=('Helvetica', 12))
    option_combobox.pack(pady=5)

    # Model frame for generation and testing model selection
    model_frame = ttk.Frame(ui_frame, style="TFrame")
    model_frame.pack(pady=10)
    ttk.Label(model_frame, text="Model for Generation:", font=('Helvetica', 14, 'bold')).grid(row=0, column=0, padx=10, pady=5)
    model_combobox = ttk.Combobox(model_frame, values=["gpt-3.5-turbo", "gpt-4-turbo", "gpt-4", "gpt-4-32k"], state="readonly", font=('Helvetica', 12))
    model_combobox.grid(row=2, column=0, padx=10, pady=5)

    ttk.Label(model_frame, text="Model for Testing:", font=('Helvetica', 14, 'bold')).grid(row=0, column=1, padx=10, pady=5)
    test_model_combobox = ttk.Combobox(model_frame, values=["gpt-3.5-turbo", "gpt-4-turbo", "gpt-4", "gpt-4-32k"], state="readonly", font=('Helvetica', 12))
    test_model_combobox.grid(row=2, column=1, padx=10, pady=5)

    # AI Temperature Slider
    ttk.Label(ui_frame, text="AI Temperature Slider:", font=('Helvetica', 14, 'bold')).pack(pady=5)
    temperature_slider = tk.Scale(ui_frame, from_=0.0, to=2.0, resolution=0.25, orient=tk.HORIZONTAL, length=300, bg="#f8f9fa", highlightthickness=0, command=update_temperature_color)
    temperature_slider.set(1)
    temperature_slider.pack(pady=10)

    # Email Chain Size Slider
    ttk.Label(ui_frame, text="Email Chain Size:", font=('Helvetica', 14, 'bold')).pack(pady=5)
    email_chain_size_slider = tk.Scale(ui_frame, from_=0, to=10, resolution=1, orient=tk.HORIZONTAL, length=300)
    email_chain_size_slider.pack(pady=10)
    email_chain_size_slider.set(0)

    # Buttons and progress bar
    button_frame = ttk.Frame(ui_frame, style="TFrame")
    button_frame.pack(pady=10)
    generate_email_button = tk.Button(button_frame, text="Generate Email", font=('Helvetica', 12), bg="white", fg="black", relief="solid", bd=2, highlightbackground="black", width=15, command=ask_email_chain_count)
    generate_email_button.grid(row=0, column=0, padx=10)
    stop_button = tk.Button(button_frame, text="Stop Generation", font=('Helvetica', 12), bg="white", fg="black", relief="solid", bd=2, highlightbackground="black", width=15, command=stop_email)
    stop_button.grid(row=0, column=1, padx=10)

    # Progress bar and label
    progress_var = tk.DoubleVar()
    progress_bar = ttk.Progressbar(ui_frame, orient='horizontal', length=300, mode='determinate', variable=progress_var)
    progress_bar.pack(pady=10)
    progress_label = ttk.Label(ui_frame, text="Progress: ", font=('Helvetica', 12), background="#f8f9fa", foreground="#666666")
    progress_label.pack()

    # Label for "Composed Email" and email display area
    ttk.Label(ui_frame, text="Composed Email:", font=('Helvetica', 14, 'bold')).pack(pady=5)
    email_display = ScrolledText(ui_frame, height=10, width=60, font=('Helvetica', 12), borderwidth=1, relief="solid", bg="#ffffff", fg="#333333", padx=10, pady=10)
    email_display.pack(pady=5)

    # Add buttons for Export and Clear Output below the email display
    output_button_frame = ttk.Frame(ui_frame, style="TFrame")
    output_button_frame.pack(pady=10)
    export_button = tk.Button(output_button_frame, text="Txt. Export Email", font=('Helvetica', 12), bg="white", fg="black", relief="solid", bd=2, highlightbackground="black", command=export_email)
    export_button.grid(row=0, column=0, padx=10)
    clear_button = tk.Button(output_button_frame, text="Clear Output", font=('Helvetica', 12), bg="white", fg="black", relief="solid", bd=2, highlightbackground="black", command=clear_output)
    clear_button.grid(row=0, column=1, padx=10)

    root.mainloop()

if __name__ == "__main__":
    show_startup()