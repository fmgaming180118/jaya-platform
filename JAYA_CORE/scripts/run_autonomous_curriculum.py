import sys
import os
import argparse
import logging
from typing import List

# Zero-Dependency .env loader (Core JAYA OS Constraint)
def load_env():
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    os.environ[k.strip()] = v.strip().strip('"').strip("'")
load_env()

# Pastikan import src/ berjalan lancar
root_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
os.chdir(root_path)
sys.path.insert(0, os.path.abspath(os.path.join(root_path, 'JAYA_CORE')))

from src.brain_v2.education.bootstrapper.auto_teacher import AutoTeacher

def main():
    parser = argparse.ArgumentParser(description="JAYA Autonomous Curriculum Bootstrapper")
    parser.add_argument("--dry-run", action="store_true", help="Jalankan di memori tanpa menulis .jay asli.")
    parser.add_argument("--topics", type=str, nargs="*", default=[], help="Topik yang akan dipelajari. Kosongkan agar JAYA memilih sendiri.")
    parser.add_argument("--continuous", action="store_true", help="Berjalan tanpa henti secara dinamis (Infinite Loop).")
    args = parser.parse_args()

    print("\n==============================================")
    print(" [INIT] JAYA AUTONOMOUS CURRICULUM ACTIVATED ")
    print("==============================================\n")
    print(f"Menginisialisasi JAYA ke dalam mode pelatihan mandiri Otonom.")
    
    if args.dry_run:
        print("[!] SAFE MODE ENGAGED. Evolusi terisolasi di Sandbox.\n")
    if args.continuous:
        print("[!] CONTINUOUS LEARNING ENGAGED. JAYA akan belajar selamanya sampai distop (Ctrl+C).\n")
    
    try:
        # Menghidupkan Otak Sang JAYA untuk belajar
        guru = AutoTeacher(use_dry_run=args.dry_run)
        
        while True:
            # Mengecek apakah Boss memberikan topik
            if not args.topics:
                print("\n[?] Membangkitkan Pillar 6: Stochastic Spontaneity...")
                active_topics = guru.ignite_curiosity(n=3)
            else:
                active_topics = args.topics
                
            print(f"\n[TARGET BELAJAR]: {', '.join(active_topics)}")
            
            # Mengekstrak Pengetahuan ke memori faktual (RAG)
            # Serta menyaring logika murni untuk masuk ke jiwa (IronEngine/.jay)
            guru.generate_and_learn_curriculum(subjects=active_topics)
            
            print("\n[SUCCESS] Siklus Kurikulum Selesai.")
            print("Data RAG telah dirapikan oleh JAYA sendiri (Otonomi).")
            print("Aksioma telah di-'sidang' oleh EvolutionGate.")
            
            if not args.continuous:
                break
            
            import time
            print("\n[WAIT] JAYA sedang beristirahat 5 detik sebelum mencari tantangan baru...")
            time.sleep(5)
            # Kosongkan argumen topik agar cycle kedua JAYA mencari topik baru sendiri
            args.topics = []
            
    except KeyboardInterrupt:
        print("\n[!] Dihentikan secara paksa oleh Boss. JAYA tertidur kembali.")
    except Exception as e:
        print(f"\n[FATAL] Terjadi kesalahan fatal pada Synapse JAYA: {e}")

if __name__ == "__main__":
    main()
