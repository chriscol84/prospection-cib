import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import google.generativeai as genai
import json

# 1. Configuration de la page
st.set_page_config(page_title="Prospection Christophe", layout="wide", page_icon="💼")

# 2. Initialisation de l'IA Gemini 2.0
model = None
if "GEMINI_API_KEY" in st.secrets:
    try:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        model = genai.GenerativeModel('gemini-2.0-flash')
    except Exception as e:
        st.error(f"Erreur configuration IA : {e}")

# 3. Connexion aux données
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=60)
def load_data():
    df = conn.read(worksheet="Prospection")
    # Nettoyage crucial des noms de colonnes (enlève les espaces invisibles)
    df.columns = [str(c).strip() for c in df.columns]
    return df.fillna("")

df = load_data()

# 4. Identification dynamique de la colonne "Nom"
# On cherche le nom exact ou une variante pour éviter le KeyError
potential_names = ["Nom (FR) (Dénomination sociale)", "Nom", "Entreprise", "Dénomination sociale"]
nom_col = next((name for name in potential_names if name in df.columns), None)

if not nom_col:
    st.error("❌ Erreur : Colonne de nom introuvable.")
    st.write("Colonnes détectées dans votre Google Sheet :", df.columns.tolist())
    st.stop()

# --- INTERFACE ---
st.title("🚀 CRM Prospection Christophe")

# Recherche latérale
search = st.sidebar.text_input(f"🔍 Rechercher une société", "")
mask = df[nom_col].str.contains(search, case=False, na=False)
filtered_df = df[mask]

# Affichage du tableau principal (Colonnes clés)
cols_vue = [nom_col, "Priorité (P1-P3)", "Secteur & Segment", "CA (M€)", "Angle d'Attaque"]
# On ne garde que les colonnes qui existent réellement pour éviter les erreurs
cols_existantes = [c for c in cols_vue if c in df.columns]
st.dataframe(filtered_df[cols_existantes], use_container_width=True, hide_index=True)

if not filtered_df.empty:
    st.divider()
    selected_company = st.selectbox("🎯 Sélectionner une société pour action :", filtered_df[nom_col].tolist())
    idx = df[df[nom_col] == selected_company].index[0]
    row = df.loc[idx]

    # --- SECTION 1 : MODIFICATION MANUELLE ---
    st.subheader("📝 Mise à jour manuelle")
    col_ed1, col_ed2 = st.columns(2)
    
    with col_ed1:
        # On essaie de récupérer la valeur actuelle de priorité
        val_priorite = str(row.get("Priorité (P1-P3)", "P3"))
        options_prio = ["P1", "P2", "P3"]
        idx_prio = options_prio.index(val_priorite) if val_priorite in options_prio else 2
        
        nouvelle_prio = st.selectbox("Priorité (P1 = Décision Benelux + Actu) :", options_prio, index=idx_prio)

    with col_ed2:
        nouvelle_accroche = st.text_area("Accroche Personnalisée / Commentaires :", value=str(row.get("Accroche Personnalisée", "")))

    if st.button("💾 Enregistrer les modifications"):
        df.at[idx, "Priorité (P1-P3)"] = nouvelle_prio
        df.at[idx, "Accroche Personnalisée"] = nouvelle_accroche
        conn.update(worksheet="Prospection", data=df)
        st.success("✅ Modifications enregistrées dans Google Sheets !")
        st.rerun()

    # --- SECTION 2 : ENRICHISSEMENT IA ---
    st.divider()
    st.subheader("🤖 Intelligence Artificielle (Gemini 2.0)")
    
    if st.button(f"🚀 Lancer l'analyse experte pour {selected_company}"):
        if model is None:
            st.error("L'IA n'est pas configurée.")
        else:
            with st.spinner("Analyse en cours..."):
                prompt = f"""
                Analyse la société {selected_company} (Secteur: {row.get('Secteur & Segment', 'N/A')}).
                Tu es un expert financier. Ne donne des infos que si tu es CERTAIN (données 2025-2026).
                Mets à jour :
                1. Controverses (ESG) : Risques récents.
                2. Dernière Actualité : M&A, levée de fonds, news stratégique.
                3. Angle d'Attaque : Trade Finance, Refi, ou Acquisition Finance.
                4. Potentiel Croissance : Score de 1 à 10.
                
                Réponds UNIQUEMENT en JSON :
                {{"esg": "...", "actu": "...", "angle": "...", "score": "..."}}
                """
                try:
                    response = model.generate_content(prompt)
                    data_ai = json.loads(response.text.replace('```json', '').replace('```', '').strip())
                    
                    # Mise à jour des colonnes qualitatives
                    if "Controverses (ESG)" in df.columns: df.at[idx, "Controverses (ESG)"] = data_ai['esg']
                    if "Dernière Actualité" in df.columns: df.at[idx, "Dernière Actualité"] = data_ai['actu']
                    if "Angle d'Attaque" in df.columns: df.at[idx, "Angle d'Attaque"] = data_ai['angle']
                    if "Potentiel Croissance" in df.columns: df.at[idx, "Potentiel Croissance"] = data_ai['score']
                    
                    conn.update(worksheet="Prospection", data=df)
                    st.success("✅ IA : Données enrichies et sauvegardées !")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erreur IA : {e}")

    # --- SECTION 3 : FICHE DE SYNTHÈSE (LISIBILITÉ) ---
    st.divider()
    st.subheader(f"🔍 Synthèse Lisible : {selected_company}")
    
    s1, s2, s3 = st.columns(3)
    with s1:
        st.write("**💰 Finances**")
        st.write(f"- CA : {row.get('CA (M€)', 'N/A')} M€")
        st.write(f"- EBITDA : {row.get('EBITDA (M€)', 'N/A')} M€")
        st.write(f"- Trésorerie : {row.get('Trésorerie (M€)', 'N/A')} M€")
    with s2:
        st.write("**🛡️ ESG & Risques**")
        st.write(f"- Controverses : {row.get('Controverses (ESG)', 'RAS')}")
        st.write(f"- Statut : {row.get('Cotée / Non Cotée', 'N/A')}")
    with s3:
        st.write("**🎯 Stratégie**")
        st.write(f"- Angle : {row.get('Angle d\'Attaque', 'À définir')}")
        st.write(f"- News : {row.get('Dernière Actualité', 'Aucune news récente')}")