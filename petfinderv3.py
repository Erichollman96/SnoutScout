import tkinter as tk
from tkinter import messagebox, ttk
from PIL import Image, ImageTk
import requests
from io import BytesIO
import threading
import sqlite3
import webbrowser
import unicodedata
import html

# ---------------- CONFIG ----------------
PETFINDER_API_KEY = "7zwmQdwo5scJ7f9K4RwxpPNMv8SGHnuOtqlj7pvNxwVXVd8HQ0"
PETFINDER_API_SECRET = "wrHWAYoRkxDI1XbbS9xL25OsPrJ2QVtW5Jxrcaac"

# Main DB connection (used only in main thread)
conn = sqlite3.connect('liked_animals.db')
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS liked (name TEXT, description TEXT, contact TEXT, image_url TEXT, animal_url TEXT)''')
conn.commit()

# ---------------- APP CLASS ----------------
class AdoptSwipeApp:
    def __init__(self, root):
        self.root = root
        self.root.title('🐾 AdoptSwipe')
        self.root.geometry('550x800')
        self.root.configure(bg='#f0f4f8')

        self.current_pet_index = 0
        self.pets = []
        self.filter_type = tk.StringVar(value='')

        # ---------------- FILTER FRAME ----------------
        filter_frame = tk.Frame(root, bg='#f0f4f8')
        filter_frame.pack(pady=5)

        tk.Label(filter_frame, text='Filter by type:', bg='#f0f4f8').grid(row=0, column=0, padx=5)
        filter_dropdown = ttk.Combobox(filter_frame, textvariable=self.filter_type,
                                       values=['', 'Dog', 'Cat', 'Rabbit', 'Small & Furry', 'Horse'],
                                       state='readonly')
        filter_dropdown.grid(row=0, column=1, padx=5)

        self.zip_code = tk.StringVar()
        tk.Label(filter_frame, text='ZIP Code:', bg='#f0f4f8').grid(row=0, column=2, padx=5)
        tk.Entry(filter_frame, textvariable=self.zip_code, width=10).grid(row=0, column=3, padx=5)

        self.distance = tk.StringVar(value='25')
        tk.Label(filter_frame, text='Max Distance (miles):', bg='#f0f4f8').grid(row=0, column=4, padx=5)
        distance_dropdown = ttk.Combobox(filter_frame, textvariable=self.distance,
                                         values=['25', '50', '100', '250', '500+'], state='readonly', width=5)
        distance_dropdown.grid(row=0, column=5, padx=5)

        tk.Button(filter_frame, text='Apply Filter', command=self.load_pets_from_api).grid(row=0, column=6, padx=5)

        # ---------------- CANVAS ----------------
        self.canvas = tk.Canvas(root, width=500, height=500, bd=0, highlightthickness=0)
        self.canvas.pack(pady=10)

        self.next_pet_image = None

        # Pet info
        self.caption_text = tk.StringVar()
        self.caption_label = tk.Label(root, textvariable=self.caption_text, wraplength=500,
                                      font=('Helvetica', 14), justify='center', bg='#f0f4f8')
        self.caption_label.pack(pady=10)

        # "View On Website" button placeholder
        self.view_button = None

        # Liked animals button
        tk.Button(root, text='Liked Animals', command=self.show_liked_animals, bg='#ffcc00').pack(pady=5)

        # Drag/swipe variables
        self.drag_data = {'x': 0, 'y': 0, 'item': None}
        self.canvas.bind('<ButtonPress-1>', self.start_drag)
        self.canvas.bind('<B1-Motion>', self.drag_image)
        self.canvas.bind('<ButtonRelease-1>', self.release_drag)

        # Load pets
        threading.Thread(target=self.load_pets_from_api).start()

    # ---------------- LOAD PETS ----------------
    def load_pets_from_api(self):
        threading.Thread(target=self._fetch_pets, daemon=True).start()

    def _fetch_pets(self):
        zip_code = self.zip_code.get().strip()
        distance = self.distance.get()

        if zip_code and (not zip_code.isdigit() or len(zip_code) != 5):
            self.root.after(0, lambda: messagebox.showerror('Invalid ZIP', 'Please enter a valid 5-digit ZIP code.'))
            return

        try:
            # Get Petfinder token
            token_url = 'https://api.petfinder.com/v2/oauth2/token'
            data = {'grant_type': 'client_credentials', 'client_id': PETFINDER_API_KEY,
                    'client_secret': PETFINDER_API_SECRET}
            response = requests.post(token_url, data=data)
            token = response.json()['access_token']

            headers = {'Authorization': f'Bearer {token}'}
            filter_query = ''
            if self.filter_type.get():
                filter_query += f'&type={self.filter_type.get()}'
            if zip_code:
                filter_query += f'&location={zip_code}'
            if distance:
                dist_value = '500' if distance == '500+' else distance
                filter_query += f'&distance={dist_value}'

            api_url = f'https://api.petfinder.com/v2/animals?limit=50{filter_query}'
            response = requests.get(api_url, headers=headers)
            fetched_pets = response.json().get('animals', [])

            # ---------------- THREAD-SAFE DB ACCESS ----------------
            conn_thread = sqlite3.connect('liked_animals.db')
            c_thread = conn_thread.cursor()
            c_thread.execute('SELECT animal_url FROM liked')
            liked_urls = {row[0] for row in c_thread.fetchall() if row[0]}
            conn_thread.close()

            # Filter out already liked pets
            self.pets = [pet for pet in fetched_pets if pet.get('url') not in liked_urls]
            self.current_pet_index = 0

            # Back to main thread to update UI
            self.root.after(0, self.show_pet)
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror('Error', f'Failed to load pets: {e}'))

    # ---------------- DISPLAY PET ----------------
    def show_pet(self):
        self.canvas.delete('all')
        self.next_pet_image = None

        if self.current_pet_index >= len(self.pets):
            messagebox.showinfo('End', 'No more pets available.')
            if self.view_button:
                self.view_button.destroy()
            return

        pet = self.pets[self.current_pet_index]

        # ---------------- NEXT PET BACKGROUND ----------------
        if self.current_pet_index + 1 < len(self.pets):
            next_pet = self.pets[self.current_pet_index + 1]
            if next_pet['primary_photo_cropped']:
                response = requests.get(next_pet['primary_photo_cropped']['small'])
                next_img = Image.open(BytesIO(response.content)).resize((500, 500))
                self.next_pet_image = ImageTk.PhotoImage(next_img)
                self.canvas.create_image(0, 0, anchor='nw', image=self.next_pet_image)

        # ---------------- CURRENT PET ----------------
        image_url = pet['primary_photo_cropped']['small'] if pet['primary_photo_cropped'] else None
        if image_url:
            response = requests.get(image_url)
            main_img = Image.open(BytesIO(response.content)).resize((500, 500))
            self.photo = ImageTk.PhotoImage(main_img)
            self.image_item = self.canvas.create_image(0, 0, anchor='nw', image=self.photo)
        else:
            # Placeholder rectangle so swiping still works
            self.image_item = self.canvas.create_rectangle(0, 0, 500, 500, fill='#cccccc')
            self.canvas.create_text(250, 250, text='No image', font=('Helvetica', 20))

        # ---------------- CAPTION ----------------
        name = unicodedata.normalize('NFKC', html.unescape(str(pet.get('name') or 'Unknown')))
        desc = unicodedata.normalize('NFKC', html.unescape(str(pet.get('description') or 'No description available.')))
        self.caption_text.set(f"{name}\n{desc}")

        # ---------------- VIEW BUTTON ----------------
        if hasattr(self, 'view_button') and self.view_button:
            self.view_button.destroy()

        pet_url = pet.get('url', '')
        if pet_url:
            self.view_button = tk.Button(self.root, text='View On Website', bg='#4caf50', fg='white',
                                         command=lambda url=pet_url: webbrowser.open(url))
            self.view_button.pack(pady=5)
        else:
            self.view_button = None

    # ---------------- DRAG HANDLERS ----------------
    def start_drag(self, event):
        self.drag_data['item'] = getattr(self, 'image_item', None)
        self.drag_data['x'] = event.x
        self.drag_data['y'] = event.y

    def drag_image(self, event):
        if not self.drag_data['item']:
            return

        coords = self.canvas.coords(self.drag_data['item'])
        if not coords:
            return

        dx = event.x - self.drag_data['x']
        dy = event.y - self.drag_data['y']
        self.canvas.move(self.drag_data['item'], dx, dy)
        self.drag_data['x'] = event.x
        self.drag_data['y'] = event.y
        x = coords[0]

        self.canvas.delete('overlay')
        if x > 100:
            self.canvas.create_text(250, 50, text='❤️', font=('Helvetica', 48), tags='overlay', fill='green')
        elif x < -100:
            self.canvas.create_text(250, 50, text='💔', font=('Helvetica', 48), tags='overlay', fill='red')

    def release_drag(self, event):
        if not self.drag_data['item']:
            return

        coords = self.canvas.coords(self.drag_data['item'])
        if not coords:
            return

        x = coords[0]
        if x > 150:
            self.swipe('yes')
        elif x < -150:
            self.swipe('no')
        else:
            self.canvas.coords(self.drag_data['item'], 0, 0)
            self.canvas.delete('overlay')

    # ---------------- SWIPE ACTION ----------------
    def swipe(self, choice):
        if self.current_pet_index >= len(self.pets):
            return

        pet = self.pets[self.current_pet_index]

        name = unicodedata.normalize('NFKC', html.unescape(str(pet.get('name') or '')))
        desc = unicodedata.normalize('NFKC', html.unescape(str(pet.get('description') or 'No description available.')))
        contact = str(pet.get('contact', {}).get('email') or 'No contact info')
        image_url = str(pet['primary_photo_cropped']['small'] if pet['primary_photo_cropped'] else '')
        animal_url = str(pet.get('url') or '')

        if choice == 'yes':
            try:
                # Use main thread connection
                c.execute('INSERT INTO liked (name, description, contact, image_url, animal_url) VALUES (?, ?, ?, ?, ?)',
                          (name, desc, contact, image_url, animal_url))
                conn.commit()
            except Exception as e:
                print("Failed to save liked pet:", e)

        self.current_pet_index += 1
        self.show_pet()

    # ---------------- LIKED ANIMALS ----------------
    def show_liked_animals(self):
        liked_window = tk.Toplevel(self.root)
        liked_window.title('❤️ Liked Animals')
        liked_window.geometry('600x600')
        liked_window.configure(bg='#f0f4f8')

        c.execute('SELECT rowid, * FROM liked')
        liked_pets = c.fetchall()

        canvas = tk.Canvas(liked_window, bg='#f0f4f8')
        scrollbar = tk.Scrollbar(liked_window, orient='vertical', command=canvas.yview)
        scroll_frame = tk.Frame(canvas, bg='#f0f4f8')
        scroll_frame.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.create_window((0,0), window=scroll_frame, anchor='nw')
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

        for idx, (rowid, name, desc, contact, image_url, animal_url) in enumerate(liked_pets):
            frame = tk.Frame(scroll_frame, bg='#e0f7fa', pady=5)
            frame.pack(fill='x', padx=10, pady=5)

            name = unicodedata.normalize('NFKC', html.unescape(str(name or 'Unknown')))
            desc = unicodedata.normalize('NFKC', html.unescape(str(desc or 'No description available.')))
            contact = unicodedata.normalize('NFKC', html.unescape(str(contact or 'No contact info')))

            tk.Label(frame, text=name, font=('Helvetica', 16, 'bold'), bg='#e0f7fa').pack(anchor='w')
            tk.Label(frame, text=desc, wraplength=550, justify='left', bg='#e0f7fa').pack(anchor='w')
            tk.Label(frame, text=f'Contact: {contact}', bg='#e0f7fa').pack(anchor='w')

            img_label = tk.Label(frame, bg='#e0f7fa')
            img_label.pack(side='left', padx=5, pady=5)

            # ---------------- LAZY LOAD IMAGE ----------------
            if image_url:
                def load_image(url=image_url, label=img_label):
                    try:
                        response = requests.get(url)
                        img = Image.open(BytesIO(response.content)).resize((150, 150))
                        photo = ImageTk.PhotoImage(img)
                        label.after(0, lambda: label.config(image=photo))
                        label.image = photo
                    except:
                        pass
                threading.Thread(target=load_image, daemon=True).start()

            # Buttons frame
            button_frame = tk.Frame(frame, bg='#e0f7fa')
            button_frame.pack(anchor='w', pady=5)

            if animal_url:
                share_button = tk.Button(button_frame, text='Share Link',
                                         command=lambda url=animal_url: webbrowser.open(url),
                                         bg='#ffcc00')
                share_button.pack(side='left', padx=5)

                view_button = tk.Button(button_frame, text='View On Website',
                                        command=lambda url=animal_url: webbrowser.open(url),
                                        bg='#4caf50', fg='white')
                view_button.pack(side='left', padx=5)

            remove_button = tk.Button(button_frame, text='Remove', bg='#e53935', fg='white',
                                      command=lambda rid=rowid, f=frame: self.remove_liked_pet(rid, f))
            remove_button.pack(side='left', padx=5)

    # ---------------- REMOVE FUNCTION ----------------
    def remove_liked_pet(self, rowid, frame):
        try:
            c.execute('DELETE FROM liked WHERE rowid=?', (rowid,))
            conn.commit()
            frame.destroy()
        except Exception as e:
            messagebox.showerror('Error', f'Failed to remove pet: {e}')

# ---------------- RUN APP ----------------
if __name__ == '__main__':
    root = tk.Tk()
    app = AdoptSwipeApp(root)
    root.mainloop()
