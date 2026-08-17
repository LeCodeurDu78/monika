"""
main.py
--------
Point d'entrée du programme Monika.
"""

from agent import run_monika, run_monika_voice
from tools.memory import warmup as warmup_embeddings

if __name__ == "__main__":
    warmup_embeddings()
    r = input("Voix ? (y/n): ").lower()
    if r == "y":
        run_monika_voice()
    else:
        run_monika()