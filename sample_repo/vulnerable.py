# Vulnerable Sample Code
import os
import subprocess


def insecure_execute(user_input):
    # RCE Vulnerability (Bandit should find this)
    os.system(user_input)


def insecure_eval(user_input):
    # Eval Vulnerability
    return eval(user_input)


def insecure_subprocess(user_input):
    # Subprocess Shell=True Vulnerability
    subprocess.run(user_input, shell=True)
