# main.py - zachowany dla zgodności: `python main.py <komenda>` == `nid2geoformats <komenda>`
import sys

from nid2geoformats.cli import main

if __name__ == "__main__":
    sys.exit(main())
