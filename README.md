# 🔥 GROUP DISTRIBUTOR!

Web application for automatic balanced group distribution of participants.

## 📋 Description

The application allows you to:
- Add a list of participants (residents)
- Automatically detect gender by name (for Russian names)
- Assign roles: Regular, VPI (VIP), Newbie
- Specify constraints (who should not be in the same group)
- Generate balanced groups considering roles and genders
- Export results to Excel

## 🚀 Quick Start

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Launch Application

```bash
streamlit run app.py
```

The application will open in your browser at `http://localhost:8501`

## 📁 Project Structure

```
.
├── app.py           # Main Streamlit application
├── generator.py     # Logic for generating balanced groups
├── names_db.py      # Database of Russian names for gender detection
└── requirements.txt # Project dependencies
```

## 🎯 Features

### Bulk Participant Import
Paste a list of names (one per line) for quick addition to the table.

### Auto Gender Detection
The application automatically detects participant gender by name using a Russian names database.

### Participant Roles
- **Regular** — standard participant
- **VPI** — VIP (Important Participant/Expert)
- **Newbie** — new participant

### Generation Settings
- Number of groups
- Strict role balance (even distribution)
- Strict gender balance (even M/F distribution)
- Seed for reproducible results

### Constraints (Boundaries)
Specify pairs of participants who should not be in the same group:
```
Oleg S: Lesha Ch, Ivan P
Anya K: Petya O, Masha I
```

### Export
Download the distribution result in Excel format (.xlsx)

## 📦 Dependencies

- **streamlit** — web framework
- **pandas** — data processing
- **openpyxl** — Excel export

## 🔧 Technical Details

### Distribution Algorithm
The generator uses random distribution with constraint checking:
- Even distribution of participants across groups (difference ≤ 1)
- Role balance between groups
- Gender balance between groups
- Personal constraints handling (who cannot be together)

### Gender Detection
The database contains common Russian names and their diminutive forms. For names not found in the database, gender must be specified manually.

## 📝 Usage Example

1. Open the application: `streamlit run app.py`
2. Paste the list of names in the bulk import field
3. Click "➕ Add to Table"
4. Edit gender and roles in the table if needed
5. Specify constraints in the "Boundaries" field
6. Configure number of groups and balance settings
7. Click "🚀 DISTRIBUTE!"
8. Download the result as Excel

## 📄 License

MIT
