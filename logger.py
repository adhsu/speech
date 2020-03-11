import logging

def main():


    # create logger with 'spam_application'
    logger = logging.getLogger('spam_application')
    logger.setLevel(logging.DEBUG)
    # create file handler which logs even debug messages
    fh = logging.FileHandler('spam.log')
    fh.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    second_func(logger)

def second_func(logger):
    logger.info('creating an instance of auxiliary_module.Auxiliary')
    logger.info('testing')




if __name__ == "__main__":
    main()