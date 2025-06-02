import os
import json
import asyncio
import threading
import tkinter as tk
from tkinter import simpledialog, messagebox, Menu, Frame, Scrollbar, Text
from PIL import Image, ImageTk
from io import BytesIO
import requests
from openai import OpenAI
import pygame
from datetime import datetime


class Configuration:
    def __init__(self):
        self.config_path = os.path.join(os.getcwd(), 'userconfig.json')
        self.config = self.load_config()

    def load_config(self):
        if not os.path.exists(self.config_path):
            return self.create_default_config()
        with open(self.config_path, 'r') as file:
            return json.load(file)

    def create_default_config(self):
        config = {
            "username": "",
            "user_id": "",
            "friends": []
        }
        self.save_config(config)
        return config

    def save_config(self, config):
        with open(self.config_path, 'w') as file:
            json.dump(config, file, indent=4)


class MainMenu:
    MUTE_SOUNDS = 0

    def __init__(self, root, config, loop):
        self.root = root
        self.config = config
        self.client = OpenAI(api_key=self.config.config["user_id"], base_url='https://api.shapes.inc/v1/')
        self.character_id = None
        self.character_name = ""
        self.character_model = ""
        self.loop = loop
        pygame.mixer.init()
        self.create_menu()
        self.create_toolbar()
        self.render_friends_list()

    def create_menu(self):
        self.root.title("Shapes.inc Instant Messenger")
        self.root.geometry("400x300")

    def create_toolbar(self):
        menubar = Menu(self.root)
        account_menu = Menu(menubar, tearoff=0)
        account_menu.add_command(label="Account Management", command=self.sign_up)
        account_menu.add_command(label="Add Friend", command=self.add_friend)
        account_menu.add_separator()
        menubar.add_cascade(label="Account", menu=account_menu)
        help_menu = Menu(menubar, tearoff=0)
        help_menu.add_command(label="Changelog", command=self.open_help_window)
        menubar.add_cascade(label="Help", menu=help_menu)
        self.root.config(menu=menubar)

    def sign_up(self):
        username = simpledialog.askstring("Account Management", "Enter your name:")
        user_id = simpledialog.askstring("Account Management", "Enter your Shapes API key:")
        if username and user_id:
            self.config.config["username"] = username
            self.config.config["user_id"] = user_id
            self.config.save_config(self.config.config)
            messagebox.showinfo("Success", "Account changes saved!")
        else:
            messagebox.showerror("Error", "Account changes failed while saving. Please try again.")

    def add_friend(self):
        if not self.config.config.get("username") or not self.config.config.get("user_id"):
            messagebox.showerror("Error", "You need to link a API key to your account.")
            return

        friend_name = simpledialog.askstring("Add Friend", "Enter your friend's name:")
        friend_id = simpledialog.askstring("Add Friend", "Enter your friend's Shapes model name\n(the username of your shape, like mrweber):")
        profile_pic_url = simpledialog.askstring("Add Friend", "Enter the URL for your friend's profile picture:")

        if friend_name and friend_id and profile_pic_url:
            try:
                response = requests.get(profile_pic_url)
                image = Image.open(BytesIO(response.content)).resize((32, 32))
                ImageTk.PhotoImage(image)
                self.config.config["friends"].append({
                    "name": friend_name,
                    "id": friend_id,
                    "profile_pic": profile_pic_url
                })
                self.config.save_config(self.config.config)
                self.render_friends_list()
                messagebox.showinfo("Success", f"Friend '{friend_name}' added successfully!")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to add friend. Error: {e}")
        else:
            messagebox.showerror("Error", "Please fill out all fields.")

    def open_help_window(self):
        win = tk.Toplevel(self.root)
        win.title("Changelog")
        win.geometry("400x300")
        tk.Label(win, text="Shapes.inc Instant Messenger", font=("Helvetica", 16)).pack(pady=10)
        tk.Label(win, text="v0.1.0 - First Public Release").pack(pady=10)

    def open_dialog_mode(self, friend):
        self.play_audio("buddyin.wav")
        self.character_id = friend['id']
        self.character_name = friend['name']
        self.character_model = f"shapesinc/{friend['id']}"
        self.display_chat_window(friend)

    def display_chat_window(self, friend):
        dialog_window = tk.Toplevel(self.root)
        dialog_window.title(f"Chat with {friend['name']}")
        dialog_window.geometry("640x480")
        dialog_window.minsize(640, 480)

        menubar = Menu(dialog_window)
        friend_menu = Menu(menubar, tearoff=0)
        friend_menu.add_command(label="Mute Sounds", command=self.toggle_sounds)
        friend_menu.add_command(label="Leave", command=lambda: self.leave_chat(dialog_window))
        menubar.add_cascade(label="Friend", menu=friend_menu)
        help_menu = Menu(menubar, tearoff=0)
        help_menu.add_command(label="Help", command=self.open_help_window)
        menubar.add_cascade(label="Help", menu=help_menu)
        dialog_window.config(menu=menubar)

        chat_frame = Frame(dialog_window)
        chat_frame.pack(fill=tk.BOTH, expand=True)
        scrollbar = Scrollbar(chat_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        chat_display = Text(chat_frame, state='disabled', wrap=tk.WORD, yscrollcommand=scrollbar.set)
        chat_display.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=chat_display.yview)
        self.load_chat_log(friend['name'], chat_display)

        input_frame = tk.Frame(dialog_window)
        input_frame.pack(pady=5)
        user_input = tk.Entry(input_frame, width=50)
        user_input.pack(side=tk.LEFT, padx=10)

        def send_message():
            message_user = user_input.get()
            if message_user.lower() == 'exit':
                dialog_window.destroy()
                return
            self.play_audio("imsend.wav")
            chat_display.config(state='normal')
            chat_display.insert(tk.END, f"You: {message_user}\n")
            chat_display.config(state='disabled')
            chat_display.see(tk.END)
            self.log_message(friend['name'], f"You: {message_user}")
            asyncio.run_coroutine_threadsafe(self.query_shapes(message_user, chat_display, friend['name']), self.loop)
            user_input.delete(0, tk.END)

        send_button = tk.Button(input_frame, text="Send", command=send_message)
        send_button.pack(side=tk.LEFT, padx=5)

    async def query_shapes(self, prompt, chat_display, friend_name):
        try:
            response = self.client.chat.completions.create(
                model=self.character_model,
                messages=[
                    {"role": "system", "content": f"You are {self.character_name}, a friendly AI."},
                    {"role": "user", "content": prompt},
                ]
            )
            reply = response.choices[0].message.content
            self.play_audio("imrcv.wav")
            chat_display.config(state='normal')
            chat_display.insert(tk.END, f"{self.character_name}: {reply}\n")
            chat_display.config(state='disabled')
            chat_display.see(tk.END)
            self.log_message(friend_name, f"{self.character_name}: {reply}")
        except Exception as e:
            print(f"Error from Shapes API: {e}")

    def load_chat_log(self, friend_name, chat_display):
        log_dir = os.path.join(os.getcwd(), "data", "chat")
        filename = os.path.join(log_dir, f"{friend_name}.txt")
        if not os.path.exists(filename):
            print(f"Log file does not exist: {filename}")
            return
        try:
            with open(filename, "r", encoding="utf-8") as file:
                chat_log = file.read()
            chat_display.config(state='normal')
            chat_display.insert(tk.END, chat_log)
            chat_display.config(state='disabled')
            chat_display.see(tk.END)
        except Exception as e:
            print(f"Error reading log file for {friend_name}: {e}")

    def log_message(self, friend_name, message):
        log_dir = os.path.join(os.getcwd(), "data", "chat")
        os.makedirs(log_dir, exist_ok=True)
        filename = os.path.join(log_dir, f"{friend_name}.txt")
        with open(filename, "a", encoding="utf-8") as file:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            file.write(f"[{timestamp}] {message}\n")

    def toggle_sounds(self):
        MainMenu.MUTE_SOUNDS = 1 - MainMenu.MUTE_SOUNDS

    def leave_chat(self, dialog_window):
        self.play_audio("buddyoff.wav")
        dialog_window.destroy()

    def play_audio(self, filename):
        if MainMenu.MUTE_SOUNDS == 0:
            audio_dir = os.path.join(os.getcwd(), "data/audio")
            filepath = os.path.join(audio_dir, filename)
            if os.path.exists(filepath):
                pygame.mixer.music.load(filepath)
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy():
                    pygame.time.Clock().tick(10)

    def render_friends_list(self):
        if hasattr(self, 'friends_frame'):
            self.friends_frame.destroy()
        self.friends_frame = tk.Frame(self.root)
        self.friends_frame.pack(fill=tk.BOTH, expand=True)
        friends = self.config.config.get("friends", [])
        for friend in friends:
            frame = tk.Frame(self.friends_frame, pady=5)
            frame.pack(fill=tk.X)
            response = requests.get(friend['profile_pic'])
            img_data = response.content
            image = Image.open(BytesIO(img_data)).resize((32, 32), Image.LANCZOS)
            photo = ImageTk.PhotoImage(image)
            img_label = tk.Label(frame, image=photo)
            img_label.image = photo
            img_label.pack(side=tk.LEFT, padx=5)
            name_label = tk.Label(frame, text=friend['name'], font=("Helvetica", 12))
            name_label.pack(side=tk.LEFT, padx=5)
            chat_button = tk.Button(frame, text="Chat", command=lambda f=friend: self.open_dialog_mode(f))
            chat_button.pack(side=tk.RIGHT, padx=5)


def main():
    root = tk.Tk()
    configuration = Configuration()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    menu = MainMenu(root, configuration, loop)
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    root.mainloop()
    loop.stop()
    thread.join()


if __name__ == '__main__':
    main()
