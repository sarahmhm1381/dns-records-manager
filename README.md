<div align="center">

# 🌐 DNS Records Manager

A lightweight full-stack web application for managing and analyzing DNS records, built with **Flask**, **MongoDB**, and **PyMongo**.  
It enables users to create, update, delete, and search DNS entries while automatically maintaining edit and deletion histories.  
The system also provides analytical aggregation on domain frequency and top-level domain distribution.

</div>

---

## 🚀 Features
- CRUD operations for DNS records (add, edit, delete, view)
- Keyword-based and prefix search functionality
- Automatic logging of deleted and edited entries
- MongoDB aggregation for:
  - Daily submission statistics  
  - Top-level domain grouping
- Simple and responsive frontend using HTML/CSS
- Modular Flask backend and clear code structure

---

## 🧠 Tech Stack
- **Backend:** Flask, PyMongo  
- **Database:** MongoDB  
- **Frontend:** HTML, CSS (Jinja2 templates)  
- **Language:** Python 3.10+

---

---

## ⚙️ Installation & Usage

### 1️⃣ Clone the repository
```bash
git clone https://github.com/sarahmhm1381/dns-records-manager.git
cd dns-records-manager

### 2️⃣ Create a virtual environment
python -m venv env
source env/bin/activate      # (Linux/Mac)
env\Scripts\activate         # (Windows)

###3️⃣ Install dependencies
pip install -r requirements.txt

### 4️⃣ Run the app
python app.py


