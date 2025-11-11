from project import CONFIG, loop
from project.bot import main

if __name__ == "__main__":
    loop.run_until_complete(main(CONFIG))
