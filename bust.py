import multiprocessing
import argparse
import signal
import time
import Queue
import sys
import os
import requests
import csv
import itertools

class ProcessURL(multiprocessing.Process):
    def __init__(self,url_queue,found_queue,url,port,ssl,sleep_time=0):
        multiprocessing.Process.__init__(self)
        self.url_queue=url_queue
        self.found_queue=found_queue
        self.sleep_time=sleep_time
        self.port=port
        self.url=url
        if ssl:
            self.proto='https://'
        else:
            self.proto='http://'

        self.headers={'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; WOW64; rv:40.0) Gecko/20100101 Firefox/40.1'}
        self.exit = multiprocessing.Event()

    def run(self):
        while not self.exit.is_set():
            try:
                data=url_queue.get(timeout=1)
                if data == "__EXIT__":
                    self.shutdown()
                else:
                    url="{0}{1}:{2}/{3}/".format(self.proto,self.url,port,data)
                    try:
                        res=requests.get(url,headers=self.headers)
                    except requests.ConnectionError:
                        self.url_queue.put(data)
                    
                    if res.status_code != 404:
                        print "URL:{0} Code:{1}".format(url,res.status_code)
                        self.found_queue.put({'url':url,'code':res.status_code})
                    time.sleep(self.sleep_time)
            except Queue.Empty:
                pass
            except KeyboardInterrupt:
                pass
        return
    
    def shutdown(self):
        print "Shutdown initiated"
        self.exit.set()
        return

class AddURL(multiprocessing.Process):
    def __init__(self,url_queue,found_queue,num_threads,brute,letters,file_name=None):
        multiprocessing.Process.__init__(self)
        self.url_queue=url_queue
        self.found_queue=found_queue
        self.num_threads=num_threads
        self.file_name=file_name
        self.brute=brute
        self.exit = multiprocessing.Event()

        self.letters=letters


    def run(self):
        try:
            if self.file_name is not None:
                with open(self.file_name) as dictionary_file:
                    for line in dictionary_file:
                        self.url_queue.put(line.strip())
                        if self.exit.is_set():
                            return
            if self.brute is not None:
                for c_len in range(1,self.brute+1):
                    for dir_name in itertools.permutations(self.letters,c_len):
                        self.url_queue.put(''.join(dir_name))

            for x in range(self.num_threads):
                self.url_queue.put("__EXIT__")

            while not self.url_queue.empty():
                time.sleep(1)

            self.found_queue.put("__EXIT__")                
            return
        except KeyboardInterrupt:
            pass
    
    def shutdown(self):
        print "Shutdown initiated"
        self.exit.set()
        return
class Logger(multiprocessing.Process):
    def __init__(self,found_queue,out_file):
        multiprocessing.Process.__init__(self)
        self.found_queue=found_queue
        self.out_file=out_file
        self.exit = multiprocessing.Event()

    def run(self):
        with open(self.out_file,'wb') as out:
            csvWriter = csv.writer(out, delimiter=',', quotechar='\\', quoting=csv.QUOTE_MINIMAL)
            while not self.exit.is_set():
                try:
                    data=self.found_queue.get(timeout=1)
                    if data == "__EXIT__":
                        return
                    else:
                        csvWriter.writerow([data['code'],data['url']])
                except Queue.Empty:
                    pass
                except KeyboardInterrupt:
                    pass
    def shutdown(self):
        print "Shutdown initiated"
        self.exit.set()
        return

if __name__ == "__main__":
    try:
        out_file='urls.csv'
        url_queue = multiprocessing.Queue(maxsize=50)
        found_queue=multiprocessing.Queue()
        workers=[]
        letters='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_~:[]@!$&\'()*+,;='
        parser = argparse.ArgumentParser(description="Directory Buster")

        parser.add_argument('-t', '--threads',
            default=1,
            type=int,
            nargs='?', help='Number of threads. Arg must be an int')

        parser.add_argument('-d', '--dictionary',
            default=None,
            nargs='?', help='Run a dictionary attack. Arg must include the dictionary file location')

        parser.add_argument('-u', '--base',
            default=None,
            required=True,
            nargs='?', help='Base URL to attack')

        parser.add_argument('-p', '--port',
            default=-1,
            type=int,
            nargs='?', help='Port of webserver')

        parser.add_argument('-s', '--ssl',
            action='store_false',
            help='Use SSL')

        parser.add_argument('-b', '--brute',
            default=None,
            type=int,
            help='Use bruteforce attack, Arg must be int. The number of character to try')

        args = parser.parse_args()

        if args.base is None:
            sys.exit("No Base URL set")

        if args.dictionary is not None and not os.path.isfile(args.dictionary):
            sys.exit("Check dictionary file")
        
        #Argparse sets args.ssl to false when added to args ????   
        if not args.ssl:
            ssl=True
            if args.port == -1:
                port=443
            else:
                port=args.port
        else:
            ssl=False
            if args.port == -1:
                port=80
            else:
                port=args.port

        brute=args.brute

        url=args.base.rstrip('/')
        
        log_thread=Logger(found_queue=found_queue,out_file=out_file)
        log_thread.start()

        workers.append(log_thread)

        add_thread=AddURL(url_queue=url_queue,found_queue=found_queue,file_name=args.dictionary,num_threads=args.threads,brute=brute,letters=letters)
        add_thread.start()

        workers.append(add_thread)

        for i in range(0,args.threads):
            p_url_thread=ProcessURL(url_queue=url_queue,found_queue=found_queue,url=url,port=port,ssl=ssl)
            p_url_thread.start()
            workers.append(p_url_thread)

        for worker in workers:
            worker.join()

        print "Done!"

    except KeyboardInterrupt:
        for worker in workers:
            worker.shutdown()