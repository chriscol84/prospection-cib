import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import google.generativeai as genai
import json

# Configuration
st.set_page_config(page_title="CRM Prospection IA", layout="wide")

# Configuration Gemini (à mettre dans vos Secrets sous le nom GEMINI_API_KEY)
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    model = genai.GenerativeModel('gemini-1.5-flash')
else:
    st.error("Clé API Gemini manquante dans les Secrets.")

conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=300)
def load_data():
    df = conn.read(worksheet="Prospection")
    df.columns = [c.strip() for c in df.columns]
    # Formatage 1 décimale pour les chiffres
    for col in df.select_dtypes(include=['number']).columns:
        df[col] = pd.to_numeric(df[col], errors='coerce').round(1)
    return df.fillna("")

df = load_data()

# --- Interface ---
st.title("💼 CRM Intelligence & Prospection")

nom_col = "Nom de l'entité"
search = st.sidebar.text_input("Rechercher une société", "")
mask = df[nom_col].str.contains(search, case=False, na=False)
filtered_df = df[mask]

# Tableau principal simplifié (vue d'ensemble)
st.dataframe(filtered_df[[nom_col, "Priorité", "Statut Follow-up", "Secteur", "CA (M€)"]], 
             use_container_width=True, hide_index=True)

if not filtered_df.empty:
    st.divider()
    selected_company = st.selectbox("Sélectionner pour analyse approfondie :", filtered_df[nom_col].tolist())
    idx = df[df[nom_col] == selected_company].index[0]
    row = df.loc[idx]

    # --- SECTION LISIBLE (Fiche de synthèse) ---
    st.subheader(f"📑 Fiche de Synthèse : {selected_company}")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.info("**Données Financières**")
        st.write(f"💰 **CA :** {row.get('CA (M€)', 'N/A')} M€")
        st.write(f"📈 **EBITDA :** {row.get('EBITDA (M€)', 'N/A')} M€")
        st.write(f"📉 **Levier :** {row.get('Levier (x)', 'N/A')}x")
    
    with col2:
        st.info("**Qualitatif & ESG**")
        st.write(f"🌿 **Stratégie ESG :** {row.get('Stratégie ESG', 'Non renseigné')}")
        st.write(f"⚠️ **Controverses :** {row.get('Controverses', 'Aucune connue')}")
    
    with col3:
        st.info("**Stratégie Commerciale**")
        st.write(f"🎯 **Angle d'Attaque :** {row.get('Angle d\'Attaque', 'À définir')}")
        st.write(f"🆕 **Dernière Actu :** {row.get('Actualité Récente', 'Aucune news')}")

    # --- BOUTON ENRICHISSEMENT IA ---
    st.write("---")
    if st.button(f"🚀 Enrichir les données de {selected_company} via Gemini"):
        with st.spinner("Analyse en cours..."):
            prompt = f"""
            Analyse la société {selected_company} opérant dans le secteur {row['Secteur']}.
            Vérifie et suggère des mises à jour uniquement si elles sont pertinentes pour :
            - Stratégie ESG
            - Controverses (Risques identifiés)
            - Dernière Actualité (Signal faible / M&A)
            - Angle d'Attaque (Trade Finance, Refi, Acquisition Finance)
            Donne une réponse précise. Si tu n'as pas de certitude, garde la valeur actuelle : "{row['Actualité Récente']}".
            Format de sortie : JSON avec les clés 'esg', 'controverses', 'actu', 'angle'.
            """
            try:
                response = model.generate_content(prompt)
                # Extraction du JSON de la réponse
                clean_res = response.text.replace('```json', '').replace('```', '').strip()
                data_ai = json.loads(clean_res)
                
                # Mise à jour des données (seulement si l'utilisateur valide ensuite ou auto-save)
                df.at[idx, 'Stratégie ESG'] = data_ai['esg']
                df.at[idx, 'Controverses'] = data_ai['controverses']
                df.at[idx, 'Actualité Récente'] = data_ai['actu']
                df.at[idx, 'Angle d\'Attaque'] = data_ai['angle']
                
                conn.update(worksheet="Prospection", data=df)
                st.success("✅ Données enrichies et synchronisées sur Google Sheets !")
                st.rerun()
            except Exception as e:
                st.error("L'IA n'a pas pu structurer la réponse. Détails : " + str(e))