#!/usr/bin/env python3

import requests

def fetch_consent_cookie_cookie_file(output_path='youtube-cookies.txt'):
    url = 'https://www.youtube.com'
    cookies = {'CONSENT': 'YES+1'}

    response = requests.get(url, cookies=cookies)

    # Extract actual cookies set by YouTube after setting consent
    session_cookies = response.cookies.get_dict()

    with open(output_path, 'w') as f:
        f.write("# Netscape HTTP Cookie File\n")
        for name, value in session_cookies.items():
            f.write(".youtube.com\tTRUE\t/\tFALSE\t0\t{}\t{}\n".format(name, value))

    print(f"Cookies written to {output_path}")

if __name__ == '__main__':
    fetch_consent_cookie_cookie_file()