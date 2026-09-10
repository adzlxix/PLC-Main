# PLC
Work functions of PLC. Inventory, shipping and ISO Documents

When work is started:
git pull

When work is done;
git add .
git commit -m "message"
git push

TO Backup file:
git checkout -b backup
git push -u origin backup
git checkout main

ON my Mac:

Every time you want to run the program, you must activate the environment:
If you close Terminal → you must reactivate.

cd /Users/adz/Documents/PLC
source .venv/bin/activate
python main.py

# PLC Inventory System

This is my custom Python-based inventory and production tracking system.  
I use it to manage all PLC-related workflows, including receiving, production, kits, and daily operations.  
The goal of this project is to keep everything simple, local, and fully under my control.

---

## What This System Does 

- Tracks all inventory inputs and outputs
- Lets me run production batches using my own CSV-driven logic
- Keeps my kits, components, and demand organized
- Logs production runs and material usage
- Lets me update, edit, and refine my logic whenever I want
- Keeps everything synchronized between my Windows laptop and Mac using GitHub

---

## Project Structure (my files)
PLC/
│── main.py
│── CHEAT_SHEET.txt
│── requirements.txt
│── README.md
│
├── data/
│   ├── Products.csv
│   ├── Kits.csv
│   ├── Components.csv
│   ├── Demand.csv
│   └── any other CSVs I need
│
├── modules/
│   ├── inventory.py
│   ├── production.py
│   ├── receiving.py
│   ├── utils.py
│   └── helpers.py
│
└── .venv/    (my virtual environment - ignored by Git)

---

## How I Run the System

Mac:
cd /Users/adz/Documents/PLC
source .venv/bin/activate
python main.py

Windows:
cd C:\Users\adam\Documents\PLC
venv\Scripts\activate
python main.py


---

## My Daily Workflow

1. Pull the latest changes  
2. Activate my venv  
3. Edit code / CSVs  
4. Run main.py to test  
5. Commit and push my updates  

I wrote a full CHEAT_SHEET.txt inside the project so I can always remind myself of the steps.

---

## Installing Dependencies

Whenever I set this project up on a new device:
This installs numpy, pandas, and everything else I use.

---

## Notes for Future Me

- Pull before editing anything  
- Keep commits small  
- Push before switching devices  
- Never commit the `.venv` folder  
- Keep all CSVs inside `/data`  
- Keep Python modules inside `/modules`  

I am building this system to grow with me over time, so I will keep the structure clean and easy to maintain.