import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import google.generativeai as genai
import json

st.set_page_config(page_title="Prospection Christophe CIB", layout="wide")

# --- INITIALISATION IA ---
model = None
if "GEMINI_API_KEY" in st.secrets:
    try:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        # Mise à jour vers le modèle 2.0 (plus stable en 2026)
        model = genai.GenerativeModel('gemini-2.0-flash')
    except Exception as e:
        st.error(f"Erreur configuration IA : {e}")

# --- CONNEXION DONNÉES ---
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=60) # Rafraîchissement toutes les minutes
def load_data():
    df = conn.read(worksheet="Prospection")
    df.columns = [c.strip() for c in df.columns]
    return df.fillna("")

df = load_data()

# --- INTERFACE ---
st.title("💼 CRM Prospection & Intelligence")

nom_col = "Nom (FR) (Dénomination sociale)" # Selon votre structure
search = st.sidebar.text_input("🔍 Rechercher une société", "")
mask = df[nom_col].str.contains(search, case=False, na=False)
filtered_df = df[mask]

st.dataframe(filtered_df, use_container_width=True, hide_index=True)

if not filtered_df.empty:
    st.divider()
    selected_company = st.selectbox("🎯 Sélectionner une société pour action :", filtered_df[nom_col].tolist())
    idx = df[df[nom_col] == selected_company].index[0]
    row = df.loc[idx]

    # --- SECTION 1 : ÉDITION MANUELLE (Statut et Commentaire) ---
    st.subheader("📝 Mise à jour manuelle")
    col_ed1, col_ed2 = st.columns(2)
    
    with col_ed1:
        # On définit les options de statut selon vos besoins
        nouveau_statut = st.selectbox("Changer le statut :", 
                                    ["À contacter", "En cours", "Opportunité", "Perdu", "Client"],
                                    index=0) # Vous pouvez adapter l'index selon la valeur actuelle
    with col_ed2:
        nouveau_commentaire = st.text_area("Ajouter un commentaire / Accroche :", 
                                          value=str(row.get('Accroche Personnalisée', '')))

    if st.button("💾 Enregistrer les modifications manuelles"):
        df.at[idx, 'Priorité (P1-P3)'] = nouveau_statut # Ajustez le nom de la colonne
        df.at[idx, 'Accroche Personnalisée'] = nouveau_commentaire
        conn.update(worksheet="Prospection", data=df)
        st.success("Données enregistrées dans Google Sheets !")
        st.rerun()

    # --- SECTION 2 : ENRICHISSEMENT IA ---
    st.divider()
    st.subheader("🤖 Analyse Intelligence Artificielle")
    
    if st.button(f"🚀 Lancer l'analyse IA pour {selected_company}"):
        if model is None:
            st.error("L'IA n'est pas configurée (Vérifiez votre clé dans les Secrets).")
        else:
            with st.spinner("Recherche de données certifiées..."):
                prompt = f"""
                Analyse {selected_company} (Secteur: {row.get('Secteur & Segment', 'N/A')}).
                Sois factuel et certain. Si inconnu, écris 'Non confirmé'.
                Donne un JSON avec : 'esg', 'controverses', 'actu', 'angle'.
                """
                try:
                    response = model.generate_content(prompt)
                    data_ai = json.loads(response.text.replace('```json', '').replace('```', '').strip())
                    
                    # Mise à jour des colonnes qualitatives
                    df.at[idx, 'Controverses (ESG)'] = data_ai['controverses']
                    df.at[idx, 'Dernière Actualité'] = data_ai['actu']
                    df.at[idx, 'Angle d\'Attaque'] = data_ai['angle']
                    
                    conn.update(worksheet="Prospection", data=df)
                    st.success("Analyse IA terminée et enregistrée !")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erreur IA : {e}")