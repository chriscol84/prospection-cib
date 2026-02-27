import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import google.generativeai as genai
import json
import time
from datetime import datetime, timedelta

# 1. CONFIGURATION DE LA PAGE
st.set_page_config(page_title="CRM Prospection Christophe", layout="wide", page_icon="💼")

# 2. INITIALISATION DE L'IA (Correction du 404)
model = None
if "GEMINI_API_KEY" in st.secrets:
    try:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        # On utilise le nom le plus standard pour éviter le 404 sur les API v1beta
        model = genai.GenerativeModel('gemini-1.5-flash') 
    except Exception as e:
        st.error(f"Erreur d'initialisation IA : {e}")

# 3. CONNEXION AUX DONNÉES GOOGLE SHEETS
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=60)
def load_data():
    df = conn.read(worksheet="Prospection")
    # Nettoyage des noms de colonnes (enlève les espaces invisibles)
    df.columns = [str(c).strip() for c in df.columns]
    return df.fillna("")

df = load_data()

# 4. SÉCURITÉ : VÉRIFICATION DE LA COLONNE NOM
nom_col = "Nom de l'entité"
if nom_col not in df.columns:
    st.error(f"❌ La colonne '{nom_col}' est introuvable.")
    st.write("Colonnes détectées :", df.columns.tolist())
    st.stop()

# --- GESTION DU DÉBIT (ANTI-BLOCAGE 6 RPM) ---
if "last_request_time" not in st.session_state:
    st.session_state.last_request_time = datetime.now() - timedelta(seconds=11)

# --- INTERFACE PRINCIPALE ---
st.title("🚀 CRM Intelligence CIB - Christophe")

# Recherche latérale
search = st.sidebar.text_input(f"🔍 Rechercher une société", "")
mask = df[nom_col].str.contains(search, case=False, na=False)
filtered_df = df[mask]

# Affichage du tableau (Vue synthétique)
cols_vue = [nom_col, "Priorité", "Statut Follow-up", "Secteur", "CA (M€)"]
cols_existantes = [c for c in cols_vue if c in df.columns]
st.dataframe(filtered_df[cols_existantes], use_container_width=True, hide_index=True)

if not filtered_df.empty:
    st.divider()
    
    selected_company = st.selectbox("🎯 Action sur la société :", filtered_df[nom_col].tolist())
    idx = df[df[nom_col] == selected_company].index[0]
    row = df.loc[idx]

    # --- SECTION 1 : MODIFICATION MANUELLE ---
    st.subheader("📝 Suivi Commercial & Commentaires")
    col_ed1, col_ed2 = st.columns(2)
    
    with col_ed1:
        options_statut = ["À contacter", "Appelé", "RDV fixé", "En cours", "Closing", "Perdu", "Client"]
        val_statut = str(row.get("Statut Follow-up", "À contacter"))
        idx_statut = options_statut.index(val_statut) if val_statut in options_statut else 0
        nouveau_statut = st.selectbox("Statut Follow-up :", options_statut, index=idx_statut)
        
        options_prio = ["P1", "P2", "P3"]
        val_prio = str(row.get("Priorité", "P3"))
        idx_prio = options_prio.index(val_prio) if val_prio in options_prio else 2
        nouvelle_prio = st.selectbox("Priorité :", options_prio, index=idx_prio)

    with col_ed2:
        nouveau_com = st.text_area("Notes de suivi :", value=str(row.get("Commentaires", "")))

    if st.button("💾 Enregistrer les modifications manuelles"):
        df.at[idx, "Statut Follow-up"] = nouveau_statut
        df.at[idx, "Priorité"] = nouvelle_prio
        df.at[idx, "Commentaires"] = nouveau_com
        conn.update(worksheet="Prospection", data=df)
        st.success("✅ Données sauvegardées dans Google Sheets !")
        st.rerun()

    # --- SECTION 2 : ENRICHISSEMENT IA (SÉCURITÉ 6 RPM) ---
    st.divider()
    st.subheader("🤖 Intelligence Marché (Gemini Flash)")
    
    now = datetime.now()
    temps_ecoule = (now - st.session_state.last_request_time).total_seconds()
    attente_restante = max(0, 11.0 - temps_ecoule) # 11s pour être très large

    if st.button(f"🚀 Lancer l'analyse IA pour {selected_company}"):
        if attente_restante > 0:
            st.warning(f"⏳ **Respect du quota (6 RPM) :** Veuillez patienter {int(attente_restante)} secondes.")
        elif model is None:
            st.error("L'IA n'est pas configurée.")
        else:
            with st.spinner(f"Analyse de {selected_company} en cours..."):
                st.session_state.last_request_time = datetime.now()
                
                # Prompt optimisé
                prompt = f"""
                Tu es expert CIB. Analyse {selected_company} (Secteur: {row.get('Secteur', 'N/A')}).
                Réponds EXCLUSIVEMENT en JSON avec : 
                'esg' (synthèse), 'actu' (news 2025-26), 'angle' (conseil Trade/Refi), 'score' (1-5).
                """
                try:
                    response = model.generate_content(prompt)
                    # Nettoyage du texte pour ne garder que le JSON
                    clean_text = response.text.strip()
                    if "```json" in clean_text:
                        clean_text = clean_text.split("```json")[1].split("```")[0]
                    elif "```" in clean_text:
                        clean_text = clean_text.split("```")[1].split("```")[0]
                    
                    res = json.loads(clean_text)
                    
                    # Mise à jour des colonnes du Sheet
                    df.at[idx, "Stratégie ESG"] = res.get('esg', '')
                    df.at[idx, "Actualité Récente"] = res.get('actu', '')
                    df.at[idx, "Angle d'Attaque"] = res.get('angle', '')
                    df.at[idx, "Potentiel (1-5)"] = res.get('score', '')
                    
                    conn.update(worksheet="Prospection", data=df)
                    st.success("✅ IA : Analyse réussie et sauvegardée !")
                    st.rerun()
                except Exception as e:
                    st.error(f"Détails de l'erreur : {e}")

    # --- SECTION 3 : FICHE DE SYNTHÈSE VISUELLE ---
    st.divider()
    st.subheader(f"🔍 Fiche Dossier : {selected_company}")
    s1, s2, s3 = st.columns(3)
    
    with s1:
        st.markdown("### 💰 Finances")
        st.write(f"**CA :** {row.get('CA (M€)', 'N/A')} M€")
        st.write(f"**EBITDA :** {row.get('EBITDA (M€)', 'N/A')} M€")
        st.write(f"**Dette Nette :** {row.get('Dette Nette (M€)', 'N/A')} M€")

    with s2:
        st.markdown("### 🌍 Stratégie & ESG")
        st.write(f"**Secteur :** {row.get('Secteur', 'N/A')}")
        st.info(f"**ESG :** {row.get('Stratégie ESG', 'Non analysé')}")
        st.error(f"**Controverses :** {row.get('Controverses', 'RAS')}")

    with s3:
        st.markdown("### 🎯 Approche")
        st.success(f"**Angle d'Attaque :** {row.get('Angle d\'Attaque', 'À définir')}")
        st.write(f"**Dernière Actu :** {row.get('Actualité Récente', 'Aucune news')}")
        st.write(f"**Potentiel :** ⭐ {row.get('Potentiel (1-5)', '0')}/5")