# SPDX-License-Identifier: MIT

from build123d import available_fonts

from utils.user_fonts import register_user_fonts

register_user_fonts()

for f in available_fonts():
    print(f)
