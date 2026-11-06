import tkinter as tk
from tkinter import ttk, messagebox
import threading
import requests

try:
    import pyttsx3
except Exception:
    pyttsx3 = None

try:
    import cv2
    import mediapipe as mp
except Exception:
    cv2 = None
    mp = None

DEFAULT_API = "http://127.0.0.1:8000"

class AssistantDesktop:
    def __init__(self, root):
        self.root = root
        self.root.title("EyeSpeak AI")
        self.root.geometry("1000x700")
        self.root.minsize(850, 600)
        self.root.configure(bg="#101827")
        self.api = DEFAULT_API
        self.token = None
        self.user = None
        self.camera_running = False
        self.cap = None
        self.face_mesh = None
        self.last_gaze_action = None
        self.gaze_since = None
        self.gaze_candidate = None
        self.gaze_grid_index = None
        self.tts = None
        if pyttsx3:
            try:
                self.tts = pyttsx3.init()
            except Exception:
                pass
        self.style()
        self.login_screen()

    def style(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("Treeview", rowheight=30, font=("Segoe UI", 10))
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))

    def clear(self):
        for w in self.root.winfo_children():
            w.destroy()

    def api_call(self, method, path, **kwargs):
        headers = kwargs.pop("headers", {})
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return requests.request(method, self.api + path, headers=headers, timeout=8, **kwargs)

    def login_screen(self):
        self.clear()
        panel = tk.Frame(self.root, bg="#172338", padx=35, pady=30)
        panel.place(relx=.5, rely=.5, anchor="center")
        tk.Label(panel, text="EYESPEAK AI COMMUNICATION", bg="#172338", fg="#f8fafc",
                 font=("Segoe UI", 20, "bold")).pack(pady=(0, 5))
        tk.Label(panel, text="Accessible care • Patient and Nurse", bg="#172338",
                 fg="#9fb0c7", font=("Segoe UI", 10)).pack(pady=(0, 22))
        self.api_entry = self.field(panel, "Server URL", DEFAULT_API)
        self.username_entry = self.field(panel, "Username", "")
        self.password_entry = self.field(panel, "Password", "", show="*")
        tk.Button(panel, text="SIGN IN", command=self.login, bg="#16a085", fg="white",
                  activebackground="#13856e", relief="flat", font=("Segoe UI", 11, "bold"),
                  padx=28, pady=10).pack(fill="x", pady=(15, 8))
        tk.Label(panel, text="Demo prototype — not a certified medical device",
                 bg="#172338", fg="#fbbf24", font=("Segoe UI", 8)).pack()

    def field(self, parent, label, value, show=None):
        tk.Label(parent, text=label, bg="#172338", fg="#cbd5e1",
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(8, 3))
        entry = tk.Entry(parent, width=38, font=("Segoe UI", 11), relief="flat",
                         bg="#f8fafc", fg="#0f172a", show=show)
        entry.pack(ipady=8)
        entry.insert(0, value)
        return entry

    def login(self):
        self.api = self.api_entry.get().strip().rstrip("/")
        try:
            r = requests.post(self.api + "/api/login", json={
                "username": self.username_entry.get().strip(),
                "password": self.password_entry.get()
            }, timeout=8)
            if r.status_code != 200:
                raise ValueError(r.json().get("detail", "Login failed"))
            data = r.json()
            self.token, self.user = data["access_token"], data["user"]
            if self.user["role"] == "patient":
                self.patient_screen()
            elif self.user["role"] in ("nurse", "admin"):
                self.nurse_screen()
            else:
                raise ValueError("Unsupported account role")
        except Exception as e:
            messagebox.showerror("Sign in failed", str(e))

    def header(self, title):
        bar = tk.Frame(self.root, bg="#172338", padx=22, pady=16)
        bar.pack(fill="x")
        tk.Label(bar, text=title, bg="#172338", fg="white",
                 font=("Segoe UI", 18, "bold")).pack(side="left")
        tk.Label(bar, text=f"{self.user['full_name']} • {self.user['role'].upper()}",
                 bg="#172338", fg="#9fb0c7", font=("Segoe UI", 9)).pack(side="right")

    def patient_screen(self):
        self.clear()
        self.header("Patient Communication")
        body = tk.Frame(self.root, bg="#101827", padx=25, pady=20)
        body.pack(fill="both", expand=True)
        tk.Label(body, text="How can we help you?", bg="#101827", fg="white",
                 font=("Segoe UI", 22, "bold")).pack(pady=(5, 18))
        grid = tk.Frame(body, bg="#101827")
        grid.pack(fill="x")
        options = [
            ("💧  I need water", "I need water"),
            ("🆘  I need help", "I need help"),
            ("👨‍⚕️  Call the nurse", "Please call the nurse"),
            ("🛏️  Change my position", "I need to change my position"),
            ("⚕️  I feel pain", "I am feeling pain"),
            ("🍽️  I need food", "I need food"),
            ("🚻  I need the toilet", "I need to use the toilet"),
            ("🧣  I am cold", "I am feeling cold"),
            ("☀️  I am too hot", "I am feeling too hot"),
            ("🛌  I need a blanket", "I need a blanket"),
            ("📞  Call my family", "Please help me call my family"),
            ("✅  I am OK", "I am OK"),
        ]
        for i, (label, text) in enumerate(options):
            btn = tk.Button(grid, text=label, command=lambda t=text: self.send_request(t),
                            bg="#20334d", fg="white", activebackground="#2d496b",
                            activeforeground="white", relief="flat",
                            font=("Segoe UI", 12, "bold"), wraplength=230, height=3)
            btn.grid(row=i//3, column=i%3, sticky="nsew", padx=7, pady=7)
        for col in range(3):
            grid.columnconfigure(col, weight=1)
        self.patient_status = tk.Label(body, text="Choose a request to notify the nurse.",
                                       bg="#101827", fg="#9fb0c7", font=("Segoe UI", 11))
        self.patient_status.pack(pady=12)
        controls = tk.Frame(body, bg="#101827")
        controls.pack(pady=8)
        tk.Button(controls, text="START EYE CAMERA", command=self.toggle_camera,
                  bg="#0f766e", fg="white", relief="flat", padx=18, pady=10).pack(side="left", padx=5)
        tk.Button(controls, text="SIGN OUT", command=self.logout,
                  bg="#475569", fg="white", relief="flat", padx=18, pady=10).pack(side="left", padx=5)
        self.camera_label = tk.Label(body, text="Camera is off", bg="#101827", fg="#64748b")
        self.camera_label.pack(pady=5)
        tk.Label(body, text="Eye gaze menu: look at one of the 12 screen directions to preview a request. Hold 1.2 seconds, press SPACE to send, or C to cancel. Q closes the camera.",
                 bg="#101827", fg="#fbbf24", font=("Segoe UI", 9), wraplength=850).pack(pady=5)
        self.root.bind("<space>", self.confirm_gaze_request)
        self.root.bind("<Key-c>", self.cancel_gaze_request)

    def speak(self, text):
        if not self.tts:
            return
        def worker():
            try:
                self.tts.say(text)
                self.tts.runAndWait()
            except Exception:
                pass
        threading.Thread(target=worker, daemon=True).start()

    def send_request(self, text, source="desktop"):
        try:
            r = self.api_call("POST", "/api/requests",
                              json={"request_text": text, "source": source})
            if r.status_code != 201:
                raise ValueError(r.json().get("detail", "Could not send request"))
            self.patient_status.config(text=f"Sent to nurse: {text}")
            self.speak(text)
        except Exception as e:
            messagebox.showerror("Request failed", str(e))

    def toggle_camera(self):
        if self.camera_running:
            self.stop_camera()
            return
        if cv2 is None or mp is None:
            messagebox.showwarning("Camera unavailable",
                "Install opencv-python and mediapipe in the Python 3.12 environment to enable eye tracking.")
            return
        try:
            self.cap = cv2.VideoCapture(0)
            if not self.cap.isOpened():
                raise RuntimeError("Camera could not be opened.")
            self.face_mesh = mp.solutions.face_mesh.FaceMesh(
                max_num_faces=1, refine_landmarks=True,
                min_detection_confidence=0.5, min_tracking_confidence=0.5
            )
            self.camera_running = True
            self.camera_label.config(text="Camera running — look LEFT for water, RIGHT for help")
            self.camera_button_state = True
            self.root.after(20, self.camera_loop)
        except Exception as e:
            self.stop_camera()
            messagebox.showerror("Camera error", str(e))

    def camera_loop(self):
        if not self.camera_running:
            return
        ok, frame = self.cap.read()
        if ok:
            frame = cv2.flip(frame, 1)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            result = self.face_mesh.process(rgb)
            action = None
            gaze_text = "Face not detected — keep your face in view"
            if result.multi_face_landmarks:
                lm = result.multi_face_landmarks[0].landmark
                # Approximate 2-D iris position relative to both eye boxes.
                # This is an experimental accessibility control, not clinical eye tracking.
                left_x = (lm[468].x - lm[33].x) / max(.001, lm[133].x - lm[33].x)
                right_x = (lm[473].x - lm[362].x) / max(.001, lm[263].x - lm[362].x)
                left_y = (lm[468].y - lm[159].y) / max(.001, lm[145].y - lm[159].y)
                right_y = (lm[473].y - lm[386].y) / max(.001, lm[374].y - lm[386].y)
                gx = (left_x + right_x) / 2
                gy = (left_y + right_y) / 2
                col = 0 if gx < .38 else (2 if gx > .62 else 1)
                row = 0 if gy < .30 else (1 if gy < .45 else (2 if gy < .60 else 3))
                idx = row * 3 + col
                # Require a reasonably clear gaze zone; center areas reduce accidental selection.
                if gx < .34 or gx > .66 or gy < .27 or gy > .63:
                    action = self.eye_options()[idx][1]
                gaze_text = f"Gaze grid: row {row+1}, column {col+1}  (x={gx:.2f}, y={gy:.2f})"
            now = time_now()
            if action:
                if self.last_gaze_action != action:
                    self.last_gaze_action, self.gaze_since = action, now
                elif self.gaze_since and now - self.gaze_since >= 1.2:
                    self.gaze_candidate = action
            else:
                self.last_gaze_action, self.gaze_since = None, None
            cv2.putText(frame, gaze_text[:90], (12, 30), cv2.FONT_HERSHEY_SIMPLEX, .48, (40, 180, 130), 1)
            prompt = (f"PREVIEW: {self.gaze_candidate} | SPACE=SEND | C=CANCEL"
                      if self.gaze_candidate else "Look toward a menu direction and hold to preview")
            cv2.rectangle(frame, (8, 48), (frame.shape[1]-8, 88), (28, 55, 75), -1)
            cv2.putText(frame, prompt[:90], (18, 75), cv2.FONT_HERSHEY_SIMPLEX, .48, (255, 255, 255), 1, cv2.LINE_AA)
            cv2.imshow("Patient Eye Camera — Q closes camera", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                self.stop_camera()
                return
        self.root.after(30, self.camera_loop)

    def eye_options(self):
        return [
            ("Water", "I need water"), ("Help", "I need help"), ("Nurse", "Please call the nurse"),
            ("Position", "I need to change my position"), ("Pain", "I am feeling pain"), ("Food", "I need food"),
            ("Toilet", "I need to use the toilet"), ("Cold", "I am feeling cold"), ("Hot", "I am feeling too hot"),
            ("Blanket", "I need a blanket"), ("Family", "Please help me call my family"), ("OK", "I am OK")
        ]

    def confirm_gaze_request(self, event=None):
        if self.camera_running and self.gaze_candidate:
            text = self.gaze_candidate
            self.gaze_candidate = None
            self.last_gaze_action = None
            self.gaze_since = None
            self.send_request(text, "eye_gaze")

    def cancel_gaze_request(self, event=None):
        self.gaze_candidate = None
        self.last_gaze_action = None
        self.gaze_since = None
        if self.camera_running:
            self.camera_label.config(text="Selection cancelled. Look toward another menu direction.")

    def stop_camera(self):
        self.camera_running = False
        self.gaze_candidate = None
        self.last_gaze_action = None
        self.gaze_since = None
        try:
            if self.cap:
                self.cap.release()
            if self.face_mesh:
                self.face_mesh.close()
            if cv2 is not None:
                cv2.destroyAllWindows()
        except Exception:
            pass
        self.cap, self.face_mesh = None, None
        if hasattr(self, "camera_label") and self.camera_label.winfo_exists():
            self.camera_label.config(text="Camera is off")

    def nurse_screen(self):
        self.clear()
        self.header("Nurse Dashboard")
        body = tk.Frame(self.root, bg="#101827", padx=20, pady=18)
        body.pack(fill="both", expand=True)
        self.summary = tk.Label(body, text="Loading summary...", bg="#101827",
                                fg="#5eead4", font=("Segoe UI", 12, "bold"))
        self.summary.pack(anchor="w", pady=(0, 12))
        cols = ("id", "patient_name", "request_text", "category", "priority", "status", "created_at")
        self.tree = ttk.Treeview(body, columns=cols, show="headings", height=14)
        for c, label, width in [
            ("id", "ID", 55), ("patient_name", "Patient", 150),
            ("request_text", "Request", 230), ("category", "AI category", 155),
            ("priority", "Priority", 85), ("status", "Status", 100),
            ("created_at", "Time", 160)
        ]:
            self.tree.heading(c, text=label)
            self.tree.column(c, width=width, anchor="w")
        self.tree.pack(fill="both", expand=True)
        buttons = tk.Frame(body, bg="#101827")
        buttons.pack(pady=12)
        tk.Button(buttons, text="MARK SEEN", command=lambda: self.update_selected("Seen"),
                  bg="#2563eb", fg="white", relief="flat", padx=18, pady=9).pack(side="left", padx=5)
        tk.Button(buttons, text="MARK RESPONDED", command=lambda: self.update_selected("Responded"),
                  bg="#0f766e", fg="white", relief="flat", padx=18, pady=9).pack(side="left", padx=5)
        tk.Button(buttons, text="REFRESH", command=self.load_requests,
                  bg="#475569", fg="white", relief="flat", padx=18, pady=9).pack(side="left", padx=5)
        tk.Button(buttons, text="SIGN OUT", command=self.logout,
                  bg="#7f1d1d", fg="white", relief="flat", padx=18, pady=9).pack(side="left", padx=5)
        self.load_requests()

    def load_requests(self):
        try:
            rows = self.api_call("GET", "/api/requests").json()
            for item in self.tree.get_children():
                self.tree.delete(item)
            for r in rows:
                self.tree.insert("", "end", values=(
                    r["id"], r["patient_name"], r["request_text"], r.get("category", "General assistance"),
                    r.get("priority", "Normal"), r["status"], r["created_at"]
                ))
            summary = self.api_call("GET", "/api/dashboard/summary").json()
            self.summary.config(text=f"TOTAL {summary['total']}     NEW {summary['new']}     "
                                     f"SEEN {summary['seen']}     RESPONDED {summary['responded']}")
        except Exception as e:
            messagebox.showerror("Dashboard error", str(e))

    def update_selected(self, state):
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("Select request", "Select a request first.")
            return
        request_id = self.tree.item(selected[0], "values")[0]
        try:
            r = self.api_call("PATCH", f"/api/requests/{request_id}", json={"status": state})
            if r.status_code != 200:
                raise ValueError(r.json().get("detail", "Update failed"))
            self.load_requests()
        except Exception as e:
            messagebox.showerror("Update failed", str(e))

    def logout(self):
        self.stop_camera()
        self.token, self.user = None, None
        self.login_screen()

def time_now():
    import time
    return time.monotonic()

if __name__ == "__main__":
    root = tk.Tk()
    AssistantDesktop(root)
    root.mainloop()
