"""All patient-app text in English and Hindi, in one place (edit translations here).

Use:  from i18n import t;  t("today")  -> text in the language chosen in the sidebar.
"""

from __future__ import annotations

import streamlit as st

TEXT = {
    # navigation / tabs
    "title": ("My health twin", "मेरा हेल्थ ट्विन"),
    "today": ("Today", "आज"),
    "medicines": ("Medicines", "दवाइयाँ"),
    "meals": ("Meals", "भोजन"),
    "my_health": ("My health", "मेरी सेहत"),
    "devices": ("Devices", "डिवाइस"),
    "ask": ("Ask my twin", "अपने ट्विन से पूछें"),
    "report": ("Report", "रिपोर्ट"),
    "language": ("Language / भाषा", "भाषा / Language"),
    "hello": ("Hello", "नमस्ते"),
    # today
    "sugar_now": ("Sugar now", "अभी शुगर"),
    "minutes_ago": ("min ago", "मिनट पहले"),
    "no_cgm": ("No sensor reading yet. Start the sensor in Devices.", "अभी कोई सेंसर रीडिंग नहीं। डिवाइस में सेंसर शुरू करें।"),
    "in_range": ("Time in range (14 days)", "सही दायरे में समय (14 दिन)"),
    "target_tir": ("Target: more than 70%", "लक्ष्य: 70% से ज़्यादा"),
    "next_dose": ("Next medicine", "अगली दवा"),
    "no_dose": ("No more medicines today", "आज और कोई दवा नहीं"),
    "taken": ("Taken", "ले ली"),
    "skip": ("Skip", "छोड़ें"),
    "due_now": ("Due now", "अभी लेनी है"),
    "low_sugar": ("Low sugar", "शुगर कम"),
    "high_sugar": ("High sugar", "शुगर ज़्यादा"),
    "good_range": ("In range", "सही दायरे में"),
    "forecast": ("In 30 minutes (estimate)", "30 मिनट में (अनुमान)"),
    "spike_warning": ("Your twin expects your sugar to go above {line} in the next 1½ hours ({p} chance). "
                      "A 15-minute walk and a smaller portion help.",
                      "आपका ट्विन अनुमान लगा रहा है कि अगले डेढ़ घंटे में शुगर {line} से ऊपर जा सकती है ({p} संभावना)। "
                      "15 मिनट टहलना और कम मात्रा में खाना मदद करता है।"),
    "new_alert": ("New alert", "नई चेतावनी"),
    "medicine_due_toast": ("Time for your medicine", "दवा लेने का समय"),
    "alerts": ("Alerts", "चेतावनियाँ"),
    # medicines
    "todays_doses": ("Today's medicines", "आज की दवाइयाँ"),
    "adherence": ("Medicines taken", "ली गई दवाइयाँ"),
    "last_7": ("last 7 days", "पिछले 7 दिन"),
    "last_30": ("last 30 days", "पिछले 30 दिन"),
    "status_taken": ("taken ✓", "ली ✓"),
    "status_missed": ("missed ✗", "छूटी ✗"),
    "status_skipped": ("skipped", "छोड़ी"),
    "status_pending": ("pending", "बाकी"),
    "with_food": ("with food", "खाने के साथ"),
    "med_note": ("Your doctor sets your medicines. Never change them on your own.",
                 "आपकी दवाइयाँ डॉक्टर तय करते हैं। अपने आप कभी न बदलें।"),
    # meals
    "log_meal": ("Log a meal", "भोजन दर्ज करें"),
    "pick_foods": ("What did you eat?", "आपने क्या खाया?"),
    "servings": ("servings", "हिस्से"),
    "save_meal": ("Save meal", "भोजन सेव करें"),
    "carbs": ("carbs", "कार्ब्स"),
    "meal_saved": ("Meal saved", "भोजन सेव हुआ"),
    "recent_meals": ("Recent meals", "हाल के भोजन"),
    "rise": ("Sugar rise after 2 h", "2 घंटे में शुगर बढ़ी"),
    "waiting": ("waiting for 2 hours of readings", "2 घंटे की रीडिंग का इंतज़ार"),
    "top_foods": ("Your top 3 spiking foods", "आपकी शुगर सबसे ज़्यादा बढ़ाने वाले 3 खाने"),
    "no_meals": ("No meals with sugar readings yet.", "अभी तक शुगर रीडिंग वाला कोई भोजन नहीं।"),
    "ask_twin_meal": ("Before you eat: ask your twin", "खाने से पहले: अपने ट्विन से पूछें"),
    "walk_after": ("Walk after eating", "खाने के बाद टहलें"),
    "no_walk": ("no walk", "नहीं टहलना"),
    "see_prediction": ("Show what my twin expects", "मेरा ट्विन क्या दिखाता है"),
    "twin_expects": ("Your twin expects your sugar to peak at", "आपके ट्विन के अनुसार आपकी शुगर सबसे ऊपर जाएगी"),
    "at": ("at", "समय"),
    "minutes_above_180": ("minutes above 180", "मिनट 180 से ऊपर"),
    "twin_knows_you": ("How well your twin knows you", "आपका ट्विन आपको कितना जानता है"),
    "twin_learnt": ("What your twin has learnt about your body", "आपके ट्विन ने आपके शरीर के बारे में क्या सीखा"),
    "per_10g": ("Your sugar rises by about {x} mg/dL for every 10 g of carbs", "हर 10 ग्राम कार्ब्स पर आपकी शुगर लगभग {x} mg/dL बढ़ती है"),
    "peaks_after": ("It is highest about {x} minutes after you eat", "खाने के लगभग {x} मिनट बाद शुगर सबसे ज़्यादा होती है"),
    "walk_lowers": ("A 15-minute walk lowers it by about {x} mg/dL", "15 मिनट टहलने से यह लगभग {x} mg/dL कम होती है"),
    "with_meal": ("with this meal", "इस भोजन के साथ"),
    "without_meal": ("without it", "इसके बिना"),
    # my health
    "hba1c_trend": ("HbA1c (3-month average sugar)", "HbA1c (3 महीने की औसत शुगर)"),
    "kidney": ("Kidney health", "किडनी की सेहत"),
    "kidney_green": ("Your kidneys are working well.", "आपकी किडनी अच्छा काम कर रही है।"),
    "kidney_yellow": ("Early signs of kidney stress. Keep sugar and BP in control.",
                      "किडनी पर हल्का दबाव। शुगर और BP नियंत्रण में रखें।"),
    "kidney_orange": ("Your kidneys need care. Follow your doctor's plan closely.",
                      "किडनी को देखभाल की ज़रूरत है। डॉक्टर की सलाह ध्यान से मानें।"),
    "kidney_red": ("Your kidneys need close care. Stay in touch with your doctor.",
                   "किडनी को खास देखभाल चाहिए। डॉक्टर के संपर्क में रहें।"),
    "bp": ("Blood pressure", "ब्लड प्रेशर"),
    "target": ("target", "लक्ष्य"),
    "what_helps": ("What you can do (your twin's estimate)", "आप क्या कर सकते हैं (ट्विन का अनुमान)"),
    "kidney_risk": ("kidney risk in 3 years", "3 साल में किडनी जोखिम"),
    "opt_bp_control": ("Bring BP to target", "BP को लक्ष्य तक लाएँ"),
    "opt_weight_loss_5pct": ("Lose 5% of body weight", "शरीर का 5% वज़न घटाएँ"),
    "opt_steps_plus_2000": ("Walk 2,000 more steps a day", "रोज़ 2,000 कदम ज़्यादा चलें"),
    "opt_stop_smoking": ("Stop smoking", "धूम्रपान छोड़ें"),
    # devices
    "sensor": ("Live sensor (demo)", "लाइव सेंसर (डेमो)"),
    "start_sensor": ("Start sensor", "सेंसर शुरू करें"),
    "stop_sensor": ("Stop sensor", "सेंसर बंद करें"),
    "sensor_on": ("Sensor is sending readings", "सेंसर रीडिंग भेज रहा है"),
    "sensor_off": ("Sensor is off", "सेंसर बंद है"),
    "libre": ("Upload FreeStyle Libre file (LibreView CSV)", "FreeStyle Libre फ़ाइल अपलोड करें (LibreView CSV)"),
    "upload": ("Upload", "अपलोड"),
    "dexcom": ("Connect Dexcom", "Dexcom जोड़ें"),
    "coming_soon": ("Coming soon", "जल्द आ रहा है"),
    "enter_readings": ("Enter home readings", "घर की रीडिंग दर्ज करें"),
    "systolic": ("BP upper (systolic)", "BP ऊपर वाला (सिस्टोलिक)"),
    "diastolic": ("BP lower (diastolic)", "BP नीचे वाला (डायस्टोलिक)"),
    "weight": ("Weight (kg)", "वज़न (किलो)"),
    "finger_glucose": ("Finger-prick sugar (mg/dL)", "उंगली से शुगर (mg/dL)"),
    "sleep": ("Sleep (hours)", "नींद (घंटे)"),
    "save": ("Save", "सेव करें"),
    "saved": ("Saved", "सेव हुआ"),
    # ask
    "summary_btn": ("Explain my health", "मेरी सेहत समझाएँ"),
    "your_question": ("Ask a question", "सवाल पूछें"),
    "offline": ("offline summary", "ऑफ़लाइन सारांश"),
    "thinking": ("Thinking...", "सोच रहा है..."),
    # report / misc
    "report_intro": ("A one-page summary in English and Hindi to keep or show your doctor.",
                     "अपने पास रखने या डॉक्टर को दिखाने के लिए अंग्रेज़ी और हिंदी में एक पेज का सारांश।"),
    "report_btn": ("Make my report", "मेरी रिपोर्ट बनाएँ"),
    "download": ("Download PDF", "PDF डाउनलोड करें"),
    "_unused_disclaimer": ("This app does not replace your doctor. Never change your medicines without talking to your doctor.",
                   "यह ऐप डॉक्टर की जगह नहीं लेता। डॉक्टर से बात किए बिना दवाइयाँ कभी न बदलें।"),
}


def lang() -> str:
    return st.session_state.get("lang", "en")


def t(key: str) -> str:
    en, hi = TEXT[key]
    return hi if lang() == "hi" else en
