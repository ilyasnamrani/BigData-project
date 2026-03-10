# -*- coding: utf-8 -*-

import os
import time
import ctypes

import numpy as np
import pandas as pd

# (Optionnel) désactiver le message oneDNN (décommente si tu veux)
# os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"

import tensorflow as tf
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense, Dropout, Input
from tensorflow.keras.callbacks import EarlyStopping, ModelCheckpoint
from tensorflow.keras.optimizers import Adam

from sklearn.preprocessing import MinMaxScaler
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

import tkinter as tk
from tkinter import filedialog, messagebox, Toplevel

import ttkbootstrap as ttk
from ttkbootstrap.constants import *

from PIL import Image, ImageTk

pd.options.mode.chained_assignment = None


# Vérifier la disponibilité du GPU
physical_devices = tf.config.list_physical_devices('GPU')
if physical_devices:
    try:
        tf.config.experimental.set_memory_growth(physical_devices[0], True)
    except Exception:
        pass
    print("GPU détecté et configuré pour TensorFlow.")
else:
    print("Aucun GPU détecté. Fonctionnement sur CPU.")


class ApplicationPredictionActions:
    def __init__(self, root):
        self.root = root
        self.root.title("PFE Prédicteur boursier")
        self.root.geometry("1400x900")

        self.style = ttk.Style()

        # Icône (safe)
        try:
            if os.name == 'nt':
                myappid = 'mycompany.myapp.subapp.version'
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

            icon_path = 'fsr2.png'  # idéalement .ico sous Windows
            if os.path.exists(icon_path):
                try:
                    # iconbitmap uniquement si .ico
                    if icon_path.lower().endswith(".ico"):
                        self.root.iconbitmap(icon_path)

                    img = Image.open(icon_path)
                    photo = ImageTk.PhotoImage(img)
                    self.root.iconphoto(False, photo)
                except Exception:
                    pass
        except Exception as e:
            print(f"Erreur de chargement de l'icône: {e}")

        # Config
        self.features = ['Fermeture', 'Volume', 'SMA20', 'RSI', 'MACD', 'BB_sup', 'BB_inf', 'ADX']
        self.scalers = {feature: MinMaxScaler(feature_range=(0, 1)) for feature in self.features}

        self.model = None
        self.full_data = None
        self.available_start = None
        self.available_end = None
        self.jours_retrospection = 30

        # Style bouton aide
        self.style.configure('Aide.TButton', background='#375a7f', foreground='white')
        self.style.map(
            'Aide.TButton',
            background=[('active', '#375a7f'), ('!active', '#375a7f')],
            foreground=[('active', 'white'), ('!active', 'white')]
        )

        # UI
        self.creer_widgets()

        # Graph
        self.fig, self.ax = plt.subplots(figsize=(12, 6), facecolor='#2d3436')
        self.ax.set_facecolor('#2d3436')
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.cadre_graphique)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Message initial résultats
        self.texte_resultats.config(state=tk.NORMAL)
        self.texte_resultats.insert(tk.END, "Les résultats apparaîtront ici après la prédiction...\n", 'info')
        self.texte_resultats.config(state=tk.DISABLED)

    def creer_widgets(self):
        conteneur_principal = ttk.Frame(self.root, padding=10)
        conteneur_principal.pack(fill=tk.BOTH, expand=True)

        # IMPORTANT: Labelframe ne supporte pas padding => padding via Frame interne
        cadre_controle = ttk.Labelframe(conteneur_principal, text="Contrôles")
        cadre_controle.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)

        controle = ttk.Frame(cadre_controle, padding=15)
        controle.pack(fill=tk.BOTH, expand=True)

        # Panneau droit graphique
        self.cadre_graphique = ttk.Frame(conteneur_principal, padding=5)
        self.cadre_graphique.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Aide
        cadre_aide = ttk.Frame(controle)
        cadre_aide.pack(side=tk.TOP, fill=tk.X, pady=(0, 10))

        self.btn_aide = ttk.Button(
            cadre_aide, text="?", width=2,
            style='Aide.TButton',
            command=self.afficher_aide
        )
        self.btn_aide.pack(side=tk.LEFT, padx=(0, 5))

        ttk.Label(
            cadre_aide,
            text="Cliquez pour l'aide",
            font=('Helvetica', 9, 'italic'),
            foreground='#aaaaaa'
        ).pack(side=tk.LEFT)

        # Données
        cadre_donnees = ttk.Labelframe(controle, text="Configuration des Données")
        cadre_donnees.pack(fill=tk.X, pady=5)

        donnees = ttk.Frame(cadre_donnees, padding=10)
        donnees.pack(fill=tk.X)

        ttk.Button(
            donnees,
            text="Charger Données",
            command=self.charger_donnees,
            bootstyle="primary",
            width=20
        ).pack(pady=5)

        # Dates
        cadre_dates = ttk.Labelframe(controle, text="Plage de Dates")
        cadre_dates.pack(fill=tk.X, pady=5)

        dates = ttk.Frame(cadre_dates, padding=10)
        dates.pack(fill=tk.X)

        ttk.Label(dates, text="Début Entraînement:").grid(row=0, column=0, sticky='w', pady=2)
        self.entree_debut_entrainement = ttk.Entry(dates, width=12)
        self.entree_debut_entrainement.grid(row=0, column=1, pady=2, padx=5)
        self.entree_debut_entrainement.insert(0, "2019-01-01")

        ttk.Label(dates, text="Début Prédiction:").grid(row=1, column=0, sticky='w', pady=2)
        self.entree_debut_prediction = ttk.Entry(dates, width=12)
        self.entree_debut_prediction.grid(row=1, column=1, pady=2, padx=5)
        self.entree_debut_prediction.insert(0, "2020-01-01")

        ttk.Label(dates, text="Date de Fin:").grid(row=2, column=0, sticky='w', pady=2)
        self.entree_date_fin = ttk.Entry(dates, width=12)
        self.entree_date_fin.grid(row=2, column=1, pady=2, padx=5)
        self.entree_date_fin.insert(0, "2020-12-31")

        # Paramètres modèle
        cadre_parametres = ttk.Labelframe(controle, text="Paramètres du Modèle")
        cadre_parametres.pack(fill=tk.X, pady=5)

        params = ttk.Frame(cadre_parametres, padding=10)
        params.pack(fill=tk.X)

        ttk.Label(params, text="Unités LSTM:").grid(row=0, column=0, sticky='w', pady=2)
        self.entree_unites = ttk.Entry(params, width=8)
        self.entree_unites.grid(row=0, column=1, pady=2, padx=5)
        self.entree_unites.insert(0, "50")

        ttk.Label(params, text="Jours de Rétrospection:").grid(row=1, column=0, sticky='w', pady=2)
        self.entree_retrospection = ttk.Entry(params, width=8)
        self.entree_retrospection.grid(row=1, column=1, pady=2, padx=5)
        self.entree_retrospection.insert(0, "30")

        # Actions
        cadre_actions = ttk.Frame(controle)
        cadre_actions.pack(fill=tk.X, pady=10)

        ttk.Button(
            cadre_actions, text="Entraîner & Prédire",
            command=self.entrainer_et_predire,
            bootstyle="success",
            width=15
        ).pack(side=tk.LEFT, padx=5)

        ttk.Button(
            cadre_actions, text="Réinitialiser",
            command=self.reinitialiser,
            bootstyle="danger",
            width=10
        ).pack(side=tk.RIGHT, padx=5)

        # Statut
        self.var_statut = tk.StringVar(value="Prêt à charger des données...")
        barre_statut = ttk.Label(self.root, textvariable=self.var_statut, anchor=tk.W)
        barre_statut.pack(side=tk.BOTTOM, fill=tk.X)

        # Progress
        self.progression = ttk.Progressbar(self.root, mode='indeterminate', bootstyle="success-striped")
        self.progression.pack(fill=tk.X, padx=10, pady=5)

        # Zone résultats (Tk Text)
        self.texte_resultats = tk.Text(self.root, height=10, wrap=tk.WORD, bg='#2d3436', fg='white')
        self.texte_resultats.pack(fill=tk.X, padx=10, pady=5)

        self.texte_resultats.tag_config('succes', foreground='#55efc4')
        self.texte_resultats.tag_config('erreur', foreground='#ff7675')
        self.texte_resultats.tag_config('info', foreground='#74b9ff')
        self.texte_resultats.tag_config('titre', foreground='#fdcb6e', font=('Helvetica', 10, 'bold'))
        self.texte_resultats.config(state=tk.DISABLED)

    def afficher_aide(self):
        fenetre_aide = Toplevel(self.root)
        fenetre_aide.title("Aide - PFE Prédicteur boursier")
        fenetre_aide.geometry("600x650")

        cadre = ttk.Frame(fenetre_aide, padding=20)
        cadre.pack(fill=tk.BOTH, expand=True)

        ttk.Label(cadre, text="Guide d'Utilisation", font=('Helvetica', 14, 'bold')).pack(pady=10)

        texte_aide = """PFE Prédicteur boursier - Mode d'emploi

1. Chargement des données:
   - Cliquez sur "Charger Données"
   - Sélectionnez un fichier CSV/Excel contenant les données historiques
   - Le fichier doit contenir les colonnes: Date, Close, Volume, High, Low

2. Configuration des dates:
   - Début Entraînement: Date de début des données d'apprentissage
   - Début Prédiction: Date à partir de laquelle faire des prédictions
   - Date de Fin: Date finale pour les prédictions

3. Paramètres du modèle:
   - Unités LSTM: Complexité du modèle (50-200 recommandé)
   - Jours de Rétrospection: Nombre de jours historiques utilisés pour chaque prédiction

4. Lancement:
   - Cliquez sur "Entraîner & Prédire" pour lancer le processus
   - Les résultats s'afficheront dans le graphique et la zone de texte

5. Visualisation:
   - Le graphique montre les données réelles et les prédictions
   - La zone de texte affiche les métriques de performance"""

        ttk.Label(cadre, text=texte_aide, justify=tk.LEFT).pack(fill=tk.BOTH, expand=True)
        ttk.Button(cadre, text="Fermer", command=fenetre_aide.destroy).pack(pady=10)

    def reinitialiser(self):
        self.model = None
        self.full_data = None
        self.available_start = None
        self.available_end = None

        self.ax.clear()
        self.canvas.draw()

        self.var_statut.set("Application réinitialisée - Prête à charger de nouvelles données")

        self.texte_resultats.config(state=tk.NORMAL)
        self.texte_resultats.delete(1.0, tk.END)
        self.texte_resultats.insert(tk.END, "Les résultats apparaîtront ici après la prédiction...\n", 'info')
        self.texte_resultats.config(state=tk.DISABLED)

    def journaliser(self, message, tag=None):
        self.texte_resultats.config(state=tk.NORMAL)
        self.texte_resultats.insert(tk.END, message + "\n", tag)
        self.texte_resultats.see(tk.END)
        self.texte_resultats.config(state=tk.DISABLED)
        self.root.update()

    def valider_dates(self, date_debut, date_pred, date_fin, jours_retrospection):
        try:
            debut = pd.to_datetime(date_debut)
            pred = pd.to_datetime(date_pred)
            fin = pd.to_datetime(date_fin)

            if debut >= pred:
                raise ValueError("La date de début doit être avant la date de prédiction")
            if pred >= fin:
                raise ValueError("La date de prédiction doit être avant la date de fin")
            if (fin - debut).days < jours_retrospection:
                raise ValueError(f"La période sélectionnée doit être d'au moins {jours_retrospection} jours")
            if (pred - debut).days < jours_retrospection:
                raise ValueError(f"La période d'entraînement doit être d'au moins {jours_retrospection} jours")
            if (fin - pred).days < 1:
                raise ValueError("La période de prédiction doit être d'au moins 1 jour")

            if self.available_start is not None and self.available_end is not None:
                if debut < self.available_start:
                    raise ValueError(f"La date de début ne peut pas être avant {self.available_start.strftime('%Y-%m-%d')}")
                if fin > self.available_end:
                    raise ValueError(f"La date de fin ne peut pas être après {self.available_end.strftime('%Y-%m-%d')}")
            return True

        except ValueError as e:
            messagebox.showerror("Erreur de Date", str(e))
            self.journaliser(f"Erreur: {str(e)}", 'erreur')
            return False

    def charger_donnees(self):
        fichier = filedialog.askopenfilename(
            filetypes=[("Fichiers CSV", ".csv"), ("Fichiers Excel", ".xlsx"), ("Tous fichiers", ".*")],
            title="Sélectionner un fichier de données boursières"
        )
        if not fichier:
            return

        try:
            self.progression.start()
            self.var_statut.set("Chargement des données...")
            self.journaliser(f"Chargement des données depuis: {fichier}", 'info')
            self.root.update()

            if fichier.lower().endswith('.csv'):
                self.full_data = pd.read_csv(
                    fichier,
                    parse_dates=['Date'],
                    index_col='Date',
                    usecols=['Date', 'Close', 'Volume', 'High', 'Low']
                )
            else:
                self.full_data = pd.read_excel(
                    fichier,
                    parse_dates=['Date'],
                    index_col='Date',
                    usecols=['Date', 'Close', 'Volume', 'High', 'Low']
                )

            self.full_data = self.full_data.rename(columns={
                'Close': 'Fermeture',
                'Volume': 'Volume',
                'High': 'Haut',
                'Low': 'Bas'
            })

            self.full_data.sort_index(inplace=True)

            self.available_start = self.full_data.index.min()
            self.available_end = self.full_data.index.max()

            self.var_statut.set(
                f"Données chargées du {self.available_start.strftime('%Y-%m-%d')} au {self.available_end.strftime('%Y-%m-%d')}"
            )

            self.journaliser("Calcul des indicateurs techniques...", 'info')

            # SMA20
            self.full_data['SMA20'] = self.full_data['Fermeture'].rolling(window=20).mean()

            # RSI
            delta = self.full_data['Fermeture'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            perte = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / perte
            self.full_data['RSI'] = 100 - (100 / (1 + rs))

            # MACD
            ema12 = self.full_data['Fermeture'].ewm(span=12, adjust=False).mean()
            ema26 = self.full_data['Fermeture'].ewm(span=26, adjust=False).mean()
            self.full_data['MACD'] = ema12 - ema26

            # Bollinger
            sma20 = self.full_data['Fermeture'].rolling(window=20).mean()
            std20 = self.full_data['Fermeture'].rolling(window=20).std()
            self.full_data['BB_sup'] = sma20 + (2 * std20)
            self.full_data['BB_inf'] = sma20 - (2 * std20)

            # ADX (approx)
            tr1 = self.full_data['Haut'] - self.full_data['Bas']
            tr2 = (self.full_data['Haut'] - self.full_data['Fermeture'].shift()).abs()
            tr3 = (self.full_data['Bas'] - self.full_data['Fermeture'].shift()).abs()
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            atr = tr.rolling(window=14).mean()

            up_move = self.full_data['Haut'] - self.full_data['Haut'].shift()
            down_move = self.full_data['Bas'].shift() - self.full_data['Bas']
            plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
            minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

            plus_dm_s = pd.Series(plus_dm, index=self.full_data.index)
            minus_dm_s = pd.Series(minus_dm, index=self.full_data.index)

            plus_di = 100 * (plus_dm_s / atr).rolling(window=14).mean()
            minus_di = 100 * (minus_dm_s / atr).rolling(window=14).mean()

            self.full_data['ADX'] = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di)).rolling(window=14).mean()

            # Remplir valeurs manquantes
            self.full_data = self.full_data.asfreq('D').ffill()
            self.full_data.dropna(inplace=True)

            self.journaliser(
                f"Données chargées avec succès - {len(self.full_data)} enregistrements avec indicateurs techniques",
                'succes'
            )

            self.afficher_graphique()

        except Exception as e:
            messagebox.showerror("Erreur", f"Échec du chargement du fichier: {str(e)}")
            self.journaliser(f"Erreur de chargement: {str(e)}", 'erreur')

        finally:
            self.progression.stop()
            self.root.update()

    def afficher_graphique(self):
        self.ax.clear()
        self.ax.set_facecolor('#2d3436')
        self.fig.set_facecolor('#2d3436')

        self.ax.plot(
            self.full_data.index,
            self.full_data['Fermeture'],
            label='Prix de Fermeture',
            color='#74b9ff',
            linewidth=2,
            alpha=0.8
        )

        self.ax.set_title('Historique des Prix Boursiers', fontsize=14, pad=10, color='white')
        self.ax.set_xlabel('Date', fontsize=12, color='white')
        self.ax.set_ylabel('Prix ($)', fontsize=12, color='white')

        self.ax.tick_params(axis='x', colors='white')
        self.ax.tick_params(axis='y', colors='white')
        self.ax.grid(True, linestyle='--', alpha=0.3, color='white')

        self.ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
        self.ax.xaxis.set_major_locator(mdates.MonthLocator())
        self.fig.autofmt_xdate()

        legende = self.ax.legend(facecolor='#2d3436', edgecolor='none')
        for t in legende.get_texts():
            t.set_color('white')

        self.canvas.draw()

    def preparer_donnees(self):
        try:
            date_debut = self.entree_debut_entrainement.get().strip()
            date_pred = self.entree_debut_prediction.get().strip()
            date_fin = self.entree_date_fin.get().strip()

            try:
                self.jours_retrospection = int(self.entree_retrospection.get())
                if not (10 <= self.jours_retrospection <= 100):
                    raise ValueError("Les jours de rétrospection doivent être entre 10 et 100")
            except ValueError as e:
                messagebox.showerror("Erreur", str(e))
                self.journaliser(f"Erreur: {str(e)}", 'erreur')
                return None, None, None, None, None

            if not self.valider_dates(date_debut, date_pred, date_fin, self.jours_retrospection):
                return None, None, None, None, None

            caracteristiques = self.features

            date_pred_etendue = pd.to_datetime(date_pred) - pd.Timedelta(days=self.jours_retrospection)
            if date_pred_etendue < pd.to_datetime(date_debut):
                date_pred_etendue = pd.to_datetime(date_debut)

            donnees_periode = self.full_data.loc[date_debut:date_fin, caracteristiques].copy()

            self.donnees_entrainement = donnees_periode.loc[date_debut:date_pred]
            self.donnees_test_etendues = donnees_periode.loc[date_pred_etendue:date_fin]
            self.donnees_test = donnees_periode.loc[date_pred:date_fin]

            if len(self.donnees_entrainement) < self.jours_retrospection:
                raise ValueError(
                    f"Pas assez de données d'entraînement. "
                    f"Besoin de {self.jours_retrospection} jours mais seulement {len(self.donnees_entrainement)} disponibles"
                )

            donnees_entrainement_scalees = np.zeros((len(self.donnees_entrainement), len(caracteristiques)))
            donnees_test_etendues_scalees = np.zeros((len(self.donnees_test_etendues), len(caracteristiques)))

            for idx, carac in enumerate(caracteristiques):
                scaler = self.scalers[carac]
                donnees_entrainement_scalees[:, idx] = scaler.fit_transform(self.donnees_entrainement[[carac]]).flatten()
                donnees_test_etendues_scalees[:, idx] = scaler.transform(self.donnees_test_etendues[[carac]]).flatten()

            X_train, y_train = self.creer_sequences(donnees_entrainement_scalees, caracteristiques.index('Fermeture'))
            X_test, y_test = self.creer_sequences(donnees_test_etendues_scalees, caracteristiques.index('Fermeture'))

            self.journaliser(
                f"Données préparées: {len(X_train)} séquences d'entraînement, {len(X_test)} séquences de test",
                'succes'
            )
            return X_train, y_train, X_test, y_test, caracteristiques

        except Exception as e:
            messagebox.showerror("Erreur", str(e))
            self.journaliser(f"Erreur préparation données: {str(e)}", 'erreur')
            return None, None, None, None, None

    def creer_sequences(self, donnees, idx_cible):
        nb = len(donnees) - self.jours_retrospection
        if nb <= 0:
            return np.array([]), np.array([])
        X = np.array([donnees[i:i + self.jours_retrospection] for i in range(nb)])
        y = donnees[self.jours_retrospection:, idx_cible]
        return X, y

    def construire_modele(self, unites, nb_caracteristiques):
        modele = Sequential([
            Input(shape=(self.jours_retrospection, nb_caracteristiques)),
            LSTM(unites, return_sequences=False),
            Dropout(0.2),
            Dense(50, activation='relu'),
            Dense(1)
        ])
        modele.compile(optimizer=Adam(learning_rate=0.001), loss='mean_squared_error')
        return modele

    def entrainer_et_predire(self):
        if self.full_data is None:
            messagebox.showerror("Erreur", "Veuillez d'abord charger des données")
            self.journaliser("Erreur: Aucune donnée chargée", 'erreur')
            return

        try:
            unites = int(self.entree_unites.get())
            if unites <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Erreur", "Valeur d'unités LSTM invalide")
            self.journaliser("Erreur: Unités LSTM invalides", 'erreur')
            return

        self.progression.start()
        self.var_statut.set("Entraînement du modèle...")
        self.journaliser("Début entraînement...", 'info')
        self.root.update()

        t0 = time.time()

        try:
            X_train, y_train, X_test, y_test, caracteristiques = self.preparer_donnees()
            if X_train is None:
                return

            nb_caracteristiques = len(caracteristiques)
            self.model = self.construire_modele(unites, nb_caracteristiques)

            # ✅ Enregistrer les WEIGHTS uniquement, puis les recharger
            checkpoint_path = "meilleur_modele.weights.h5"
            checkpoint = ModelCheckpoint(
                checkpoint_path,
                monitor='loss',
                save_best_only=True,
                save_weights_only=True
            )
            early = EarlyStopping(monitor='loss', patience=5)

            self.journaliser("Entraînement en cours...", 'info')
            hist = self.model.fit(
                X_train, y_train,
                batch_size=32,
                epochs=50,
                callbacks=[early, checkpoint],
                verbose=0
            )

            # ✅ Recharger les meilleurs weights
            self.model.load_weights(checkpoint_path)

            self.var_statut.set("Prédiction en cours...")
            self.journaliser("Prédiction...", 'info')
            self.root.update()

            preds = self.model.predict(X_test, verbose=0, batch_size=32)
            preds = self.scalers['Fermeture'].inverse_transform(preds)
            reels = self.scalers['Fermeture'].inverse_transform(y_test.reshape(-1, 1))

            dates_pred = self.donnees_test_etendues.index[self.jours_retrospection:]
            if len(dates_pred) != len(preds):
                raise ValueError(
                    f"Longueur prédictions ({len(preds)}) != longueur dates ({len(dates_pred)})"
                )

            resultats = pd.DataFrame({
                'Date': dates_pred,
                'Réel': reels.flatten(),
                'Prédit': preds.flatten()
            })

            date_pred = pd.to_datetime(self.entree_debut_prediction.get())
            resultats_filtres = resultats[resultats['Date'] >= date_pred].copy()

            # =========================
            # ✅ MÉTRIQUES (MSE, RMSE, MAE, R2, MAPE)
            # =========================
            y_true = resultats_filtres['Réel'].values
            y_pred = resultats_filtres['Prédit'].values

            mse = mean_squared_error(y_true, y_pred)
            rmse = np.sqrt(mse)
            mae = mean_absolute_error(y_true, y_pred)
            r2 = r2_score(y_true, y_pred)

            denom = np.where(y_true == 0, np.nan, y_true)
            mape = np.nanmean(np.abs((y_true - y_pred) / denom)) * 100

            t_train = time.time() - t0

            # =========================
            # ✅ AFFICHAGE (comme MAPE/RMSE)
            # =========================
            self.texte_resultats.config(state=tk.NORMAL)
            self.texte_resultats.delete(1.0, tk.END)

            self.texte_resultats.insert(tk.END, "=== Résultats d'Entraînement ===\n", 'titre')
            self.texte_resultats.insert(tk.END, f"Temps total: {t_train:.2f} s\n")
            self.texte_resultats.insert(tk.END, f"Perte finale: {hist.history['loss'][-1]:.6f}\n\n")

            self.texte_resultats.insert(tk.END, "=== Métriques ===\n", 'titre')
            self.texte_resultats.insert(tk.END, f"MAPE: {mape:.2f}%\n", 'succes')
            self.texte_resultats.insert(tk.END, f"RMSE: {rmse:.4f}\n", 'succes')
            self.texte_resultats.insert(tk.END, f"MSE : {mse:.4f}\n", 'succes')
            self.texte_resultats.insert(tk.END, f"MAE : {mae:.4f}\n", 'succes')
            self.texte_resultats.insert(tk.END, f"R²  : {r2:.4f}\n\n", 'succes')

            self.texte_resultats.insert(tk.END, "=== 10 Dernières Prédictions ===\n", 'titre')
            self.texte_resultats.insert(tk.END, resultats_filtres.tail(10).to_string(index=False))
            self.texte_resultats.config(state=tk.DISABLED)

            self.afficher_resultats(resultats)
            self.var_statut.set("Prédiction terminée ✅")
            self.journaliser("Prédiction terminée avec succès!", 'succes')

        except Exception as e:
            messagebox.showerror("Erreur", f"Une erreur est survenue: {str(e)}")
            self.var_statut.set("Erreur survenue")
            self.journaliser(f"Erreur: {str(e)}", 'erreur')

        finally:
            self.progression.stop()
            self.root.update()

    def afficher_resultats(self, resultats):
        self.ax.clear()

        donnees_periode = self.full_data.loc[
            self.entree_debut_entrainement.get():self.entree_date_fin.get()
        ]
        date_pred = pd.to_datetime(self.entree_debut_prediction.get())

        train = donnees_periode[donnees_periode.index < date_pred]
        test = donnees_periode[donnees_periode.index >= date_pred]

        self.ax.plot(train.index, train['Fermeture'], label="Entraînement", color='#74b9ff', linewidth=2, alpha=0.8)
        self.ax.plot(test.index, test['Fermeture'], label="Réel", color='#55efc4', linewidth=2, alpha=0.8)
        self.ax.plot(resultats['Date'], resultats['Prédit'], label="Prédit", color='#ff7675', linestyle='--', linewidth=2)

        self.ax.axvline(x=date_pred, color='#a29bfe', linestyle=':', alpha=0.7)
        self.ax.text(date_pred, self.ax.get_ylim()[1] * 0.9, 'Début Prédiction', color='white', rotation=90, va='top')

        self.ax.set_title('Résultats de Prédiction Boursière', fontsize=14, pad=10, color='white')
        self.ax.set_xlabel('Date', fontsize=12, color='white')
        self.ax.set_ylabel('Prix ($)', fontsize=12, color='white')

        self.ax.tick_params(axis='x', colors='white')
        self.ax.tick_params(axis='y', colors='white')
        self.ax.grid(True, linestyle='--', alpha=0.3, color='white')

        self.ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
        self.ax.xaxis.set_major_locator(mdates.MonthLocator())
        self.fig.autofmt_xdate()

        leg = self.ax.legend(facecolor='#2d3436', edgecolor='none')
        for t in leg.get_texts():
            t.set_color('white')

        self.canvas.draw()


if __name__ == "__main__":
    root = ttk.Window(themename="darkly")
    app = ApplicationPredictionActions(root)
    root.mainloop()
