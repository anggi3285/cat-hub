# 🐾 Mimi's Couple Cat Room (Virtual Pet Tamagotchi)

A real-time shared virtual cat room web application designed for couples. Co-parent Mimi the cat together with real-time care mechanics, daily couple prompts, and a sticky notes love diary.

Built with **Python Flask**, **Flask-SocketIO**, SQLite, and modern vanilla HTML5/CSS3/JavaScript.

---

## ✨ Features

- 🐱 **Couple Shared Tamagotchi:** Both partners co-parent one pet with synchronized status bars (Hunger, Happiness, Energy, and Cleanliness).
- 🐾 **Pet Evolution Stages:** Mimi grows as Love Points increase (`Kitten` ➔ `Teen Cat` ➔ `Adult Cat`).
- 🎮 **6 Interactive Pet Actions:**
  - 🐟 **Feed:** Boost hunger & happiness.
  - ✋ **Pet:** Soothe and hear Mimi purr.
  - 🛁 **Bath:** Keep Mimi clean and fresh.
  - 🧶 **Play:** Play with yarn ball (costs energy, gives high happiness).
  - 💤 **Sleep / Wake:** Recharges energy.
  - 💌 **Send Hug:** Send an instant virtual hug & love notification to your partner.
- 💬 **Daily Couple Prompts:** Lightweight daily relationship conversation questions answered together.
- 📝 **Sticky Notes Diary:** Real-time notes wall with custom pastels.
- 🪴 **Unlockable Room Decor:** Ambient fairy lights, rainy window view, plant pots, and cozy rugs unlocked via progression.
- ⚡ **Real-Time WebSocket Sync:** Powered by Socket.IO for seamless instant state updates across mobile & desktop browsers.

---

## 🚀 Getting Started

### 1. Clone repository
```bash
git clone https://github.com/anggi3285/cat-hub.git
cd cat-hub
```

### 2. Setup Virtual Environment & Install Dependencies
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Run Application
```bash
python3 server.py
```
Open browser at: `http://localhost:5000`
