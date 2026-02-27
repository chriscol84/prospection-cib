import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import google.generativeai as genai
import json

# 1. Configuration de la page
st.set_page_config(page_title="Prospection Christophe CIB", layout="wide", page_icon="💼")

# 2. Initialisation de l'IA Gemini 2.0
model = None
if "GEMINI_API_KEY" in st.secrets:
    try:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        model = genai.GenerativeModel('gemini-2.0-flash')
    except Exception as e:
        st.error(f"Erreur d'initialisation IA : {e}")

# 3. Connexion aux données Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=60)
def load_data():
    # Lecture de l'onglet "Prospection"
    df = conn.read(worksheet="Prospection")
    # Nettoyage des noms de colonnes pour éviter les espaces invisibles
    df.columns = [str(c).strip() for c in df.columns]
    return df.fillna("")

df = load_data()

# 4. Identification de la colonne Nom (Vérification stricte de votre liste)
nom_col = "Nom de l'entité"

if nom_col not in df.columns:
    st.error(f"❌ La colonne '{nom_col}' est introuvable.")
    st.write("Colonnes détectées :", df.columns.tolist())
    st.stop()

# --- INTERFACE PRINCIPALE ---
st.title("🚀 CRM Intelligence CIB - Prospection Christophe")

# Recherche latérale
search = st.sidebar.text_input(f"🔍 Rechercher une société", "")
mask = df[nom_col].str.contains(search, case=False, na=False)
filtered_df = df[mask]

# Affichage du tableau principal (Colonnes stratégiques uniquement)
cols_a_afficher = [nom_col, "Priorité", "Statut Follow-up", "Secteur", "CA (M€)"]
cols_existantes = [c for c in cols_a_afficher if c in df.columns]
st.dataframe(filtered_df[cols_existantes], use_container_width=True, hide_index=True)

if not filtered_df.empty:
    st.divider()
    
    # Sélection de la société cible
    selected_company = st.selectbox("🎯 Action sur la société :", filtered_df[nom_col].tolist())
    idx = df[df[nom_col] == selected_company].index[0]
    row = df.loc[idx]

    # --- SECTION 1 : MISE À JOUR MANUELLE ---
    st.subheader("📝 Suivi Commercial & Commentaires")
    col_ed1, col_ed2 = st.columns(2)
    
    with col_ed1:
        # Gestion dynamique du Statut
        options_statut = ["À contacter", "Appelé", "RDV fixé", "En cours", "Closing", "Perdu", "Client"]
        val_actuelle = str(row.get("Statut Follow-up", "À contacter"))
        idx_statut = options_statut.index(val_actuelle) if val_actuelle in options_statut else 0
        nouveau_statut = st.selectbox("Statut Follow-up :", options_statut, index=idx_statut)
        
        # Gestion dynamique de la Priorité
        options_prio = ["P1", "P2", "P3"]
        val_prio = str(row.get("Priorité", "P3"))
        idx_prio = options_prio.index(val_prio) if val_prio in options_prio else 2
        nouvelle_prio = st.selectbox("Priorité (P1-P3) :", options_prio, index=idx_prio)

    with col_ed2:
        nouveau_com = st.text_area("Commentaires / Notes de suivi :", value=str(row.get("Commentaires", "")))

    if st.button("💾 Enregistrer les modifications manuelles"):
        df.at[idx, "Statut Follow-up"] = nouveau_statut
        df.at[idx, "Priorité"] = nouvelle_prio
        df.at[idx, "Commentaires"] = nouveau_com
        conn.update(worksheet="Prospection", data=df)
        st.success("✅ Données manuelles sauvegardées dans Google Sheets !")
        st.rerun()

    # --- SECTION 2 : ENRICHISSEMENT IA (AVEC GESTION QUOTA 429) ---
    st.divider()
    st.subheader("🤖 Intelligence Artificielle (Analyse Stratégique)")
    
    if st.button(f"🚀 Lancer l'analyse experte pour {selected_company}"):
        if model is None:
            st.error("L'IA n'est pas configurée.")
        else:
            with st.spinner("Analyse approfondie en cours..."):
                prompt = f"""
                Tu es un analyste CIB expert. Analyse la société {selected_company}.
                Secteur: {row.get('Secteur', 'N/A')}.
                Réponds EXCLUSIVEMENT en JSON avec ces clés : 
                'esg' (synthèse stratégie), 'actu' (news 2025-26), 'angle' (conseil approche Trade/Refi), 'score' (potentiel 1-5).
                """
                try:
                    response = model.generate_content(prompt)
                    res = json.loads(response.text.replace('```json', '').replace('```', '').strip())
                    
                    # Mise à jour des colonnes qualitatives du Sheet
                    df.at[idx, "Stratégie ESG"] = res['esg']
                    df.at[idx, "Actualité Récente"] = res['actu']
                    df.at[idx, "Angle d'Attaque"] = res['angle']
                    df.at[idx, "Potentiel (1-5)"] = res['score']
                    
                    conn.update(worksheet="Prospection", data=df)
                    st.success("✅ Analyse IA intégrée avec succès !")
                    st.rerun()
                except Exception as e:
                    if "429" in str(e):
                        st.error("🛑 Quota atteint. Attendez 60 secondes avant de réessayer.")
                    else:
                        st.error(f"Erreur IA : {e}")

    # --- SECTION 3 : FICHE DE SYNTHÈSE VISUELLE (TABLEAU DE BORD) ---
    st.divider()
    st.subheader(f"🔍 Fiche Qualitative : {selected_company}")
    
    s1, s2, s3 = st.columns(3)
    with s1:
        st.markdown("### 💰 Données Financières")
        st.write(f"**CA :** {row.get('CA (M€)', 'N/A')} M€")
        st.write(f"**EBITDA :** {row.get('EBITDA (M€)', 'N/A')} M€")
        st.write(f"**Dette Nette :** {row.get('Dette Nette (M€)', 'N/A')} M€")
        st.write(f"- Trésorerie : {row.get('Trésorerie (M€)', 'N/A')} M€")
        st.write(f"- Statut : {row.get('Statut / Sponsor PE', 'N/A')}")

    with s2:
        st.markdown("### 🌍 Stratégie & ESG")
        st.write(f"**Secteur :** {row.get('Secteur', 'N/A')}")
        st.write(f"**Siège :** {row.get('Siège de Décision', 'N/A')}")
        st.info(f"**ESG :** {row.get('Stratégie ESG', 'Non analysé')}")
        st.error(f"**Controverses :** {row.get('Controverses', 'RAS')}")

    with s3:
        st.markdown("### 🎯 Approche Commerciale")
        st.success(f"**Angle d'Attaque :** {row.get('Angle d\'Attaque', 'À définir')}")
        st.write(f"**Dernière Actu :** {row.get('Actualité Récente', 'Aucune news')}")
        st.write(f"**Potentiel :** ⭐ {row.get('Potentiel (1-5)', '0')}/5")
        st.write(f"**Maturité Crédit :** {row.get('Maturité de Crédit (Source)', 'N/A')}")