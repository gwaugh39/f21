import sys, json, io, time, traceback, itertools, re, os, math, base64, csv
import traceback, csv, struct, socket, subprocess
from collections import namedtuple, defaultdict
from datetime import datetime, timedelta
from matplotlib import pyplot as plt
from io import StringIO, BytesIO
from bs4 import BeautifulSoup
import pandas as pd
import numpy as np
from zipfile import ZipFile, ZIP_DEFLATED
from io import TextIOWrapper
from xml.dom import minidom

########################################
# TEST FRAMEWORK
########################################

TestFunc = namedtuple("TestFunc", ["fn", "points"])
tests = []

prog_name = "main.py"

# if @test(...) decorator is before a function, add that function to test_fucns
def test(points):
    def add_test(fn):
        tests.append(TestFunc(fn, points))
        return fn
    return add_test

# override print so can also capture output for results.json
print_buf = None
orig_print = print
def print(*args, **kwargs):
    orig_print(*args, **kwargs)
    if print_buf != None:
        orig_print(*args, **kwargs, file=print_buf)

# both are simple name => val
# expected_json <- expected.json (before tests)
# actual_json -> actual.json (after tests)
#
# TIP: to generate expected.json, run the tests on a good
# implementation, then copy actual.json to expected.json
expected_json = None
actual_json = {"version": 1}

# return string (error) or None
def is_expected2(actual, name, histo_comp=False):
    global expected_json

    actual_json[name] = actual
    if expected_json == None:
        with open("expected.json") as f:
            expected_json = json.load(f)

    expected = expected_json.get(name, None)
    
    # for hist_comp, we don't care about order of the two list like
    # objects.  We just care that the two histograms are similar.
    if histo_comp:
        if actual == None or expected == None:
            return ("invalid histo_comp types: {}, {}".format(type(actual), type(expected)))
        
        if len(actual) != len(expected):
            return "expected {} points but found {} points".format(len(expected), len(actual))
        diff = 0
        actual = sorted(actual)
        expected = sorted(expected)
        for a, e in zip(actual, expected):
            diff += abs(a - e)
        diff /= len(expected)
        if diff > 0.01:
            return "average error between actual and expected was %.2f (>0.01)" % diff

    elif type(expected) != type(actual) and expected != None and actual != None:
        return "expected a {} but found {} of type {}".format(expected, actual, type(actual))

    elif expected != actual:
        return "expected {} but found {}".format(expected, actual)

    return None

# wraps is_expected, just adds name to error messages
def is_expected(actual, name, histo_comp=False):
    err = is_expected2(actual, name, histo_comp)
    if err:
        return f"{err} [BAD {name}]"
    return None

# execute every function with @test decorator; save results to results.json
def run_all_tests():
    global print_buf
    global expected_json
    print("Running tests...")

    results = {'score':0, 'tests': [], 'lint': [], "date":datetime.now().strftime("%m/%d/%Y")}
    total_points = 0
    total_possible = 0

    t0 = time.time()
    for t in tests:
        print_buf = StringIO() # trace prints
        print("="*40)
        print("TEST {} ({} points possible)".format(t.fn.__name__, t.points))
        try:
            points = t.fn()
        except subprocess.CalledProcessError as exc:
            print(exc.returncode, exc.output)
            points = 0
        except Exception as e:
            print(traceback.format_exc())
            points = 0
        if points > t.points:
            raise Exception("got {} points on {} but expected at most {}".format(points, t.fn.__name__, t.points))
        total_points += points
        total_possible += t.points
        row = {"test": t.fn.__name__, "points": points, "possible": t.points}
        if points != t.points:
            row["log"] = print_buf.getvalue().split("\n")
        results["tests"].append(row)
        print_buf = None # stop tracing prints
        print("TEST RESULT: {} of {} points".format(points, t.points))

    
    # how long did it take?
    t1 = time.time()
    max_sec = 240
    sec = t1-t0
           
    print("="*40)
    print("Earned {} of {} points across all tests".format(total_points, total_possible))
    results["score"] = round(100.0 * total_points / total_possible, 1)

    results["latency"] = sec

    # output results
    with open("results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    with open("actual.json", "w", encoding="utf-8") as f:
        json.dump(actual_json, f, indent=2)

    print("="*40)
    print("SCORE: %.1f%% (details in results.json)" % results["score"])
    
    # open expected
    with open("expected.json") as f:
        expected_json = json.load(f)

    # does tester.py version match expected.json version?
    if actual_json["version"] != expected_json["version"]:
        print("#"*80)
        print("#"*80)
        print("#")
        if actual_json["version"] > expected_json["version"]:
            print("# WARING! There's a newer version of expected.json, please re-download")
        else:
            print("# WARING! There's a newer version of tester.py, please re-download")
        print("#")
        print("#"*80)
        print("#"*80)

########################################
# TESTS
########################################

header = "ip,date,time,zone,cik,accession,extention,code,size,idx,norefer,noagent,find,crawler,browser".split(",")
ip_idx = header.index("ip")
date_idx = header.index("date")
time_idx = header.index("time")
cik_idx = header.index("cik")
accession_idx = header.index("accession")

def gen(row_count=10, sort=False, name=None):
    # name of test that called this
    if name == None:
        name = traceback.extract_stack()[-2].name

    ip_part = 1
    def next_ip_part():
        nonlocal ip_part
        ip_part *= 13
        ip_part %= 256
        return str(ip_part)

    def next_ip():
        ip = ".".join([next_ip_part() for i in range(3)])
        anon = "".join(["abcdefghij"[int(c)] for c in next_ip_part()])
        return ip + "." + anon

    # https://stackoverflow.com/questions/9590965/convert-an-ip-string-to-a-number-and-vice-versa
    def fill_accession(row):
        orig = row[ip_idx][:row[ip_idx].rindex(".")]+".000"
        row[accession_idx] = struct.unpack("!L", socket.inet_aton(orig))[0]

    rows = []
    seconds = 0
    for i in range(row_count):
        row = ["?" for i in range(len(header))]
        row[ip_idx] = next_ip()
        row[date_idx] = "2017-01-01"
        seconds = (seconds * 17) % (24 * 60 * 60)
        row[time_idx] = "%02d:%02d:%02d" % ((seconds//3600) % 24, (seconds//60) % 60, seconds % 60)
        row[cik_idx] = "cik"+str(i)
        fill_accession(row)
        rows.append(row)

    if sort:
        rows.sort(key=lambda row: row[accession_idx])

    zipname = name+".zip"
    with ZipFile(zipname, "w", compression=ZIP_DEFLATED) as zf:
        with zf.open(name+".csv", "w") as raw:
            with TextIOWrapper(raw) as f:
                writer = csv.writer(f, lineterminator='\n')
                writer.writerow(header)
                for row in rows:
                    writer.writerow(row)
    return zipname

def svg_analyze(fname):
    doc = minidom.parse(fname)
    
    stats = {
        "paths": 0,
        "colors": set(),
        "width": float(doc.getElementsByTagName("svg")[0].getAttribute("width").replace("pt", ""))
    }

    rgb = [0, 0, 0]

    for path in doc.getElementsByTagName('path'):
        style = path.getAttribute('style')

        m = re.match(r"fill:\#(\w+)\;", style)
        if m:
            color = m.group(1).lower()
            if color == "ffffff":
                continue
            stats["colors"].add(color)
            for i in range(3):
                rgb[i] += int(color[i*2:(i+1)*2], 16)
        else:
            continue
        stats["paths"] += 1

    stats["colors"] = len(stats["colors"])
    rgb = "".join([format(int(c/stats["paths"]), "x") for c in rgb])
    stats["avg_color"] = rgb
    return stats

def run(*args):
    args = ["python3", prog_name] + [str(a) for a in args] 
    print("RUN:", " ".join(args))
    output = subprocess.check_output(
        args, stderr=subprocess.STDOUT,
        timeout=30, # add time limit
        universal_newlines=True
    )
    return output


def zip_csv_iter(name):
    with ZipFile(name) as zf:
        with zf.open(name.replace(".zip", ".csv")) as f:
            reader = csv.reader(TextIOWrapper(f))
            for row in reader:
                yield row

def check_zip(zname):
    rows = list(zip_csv_iter(zname))
    errors = [is_expected(len(rows)-1, zname+":length")]

    for i, row in enumerate(rows):
        errors.append(is_expected(len(rows), zname+":row-%d:length" % i))

        ip = row[ip_idx]
        cik = row[cik_idx]
        errors.append(is_expected(ip, zname+":row-%d:ip" % i))
        errors.append(is_expected(cik, zname+":row-%d:cik" % i))

    errors = [e for e in errors if e != None]
    if errors:
        return errors[0]
    return None

def zip_csv_iter(name):
    with ZipFile(name) as zf:
        with zf.open(name.replace(".zip", ".csv")) as f:
            reader = csv.reader(TextIOWrapper(f))
            for row in reader:
                yield row

@test(points=25)
def ip_check():
    points = 25
    ip_list = ["1.1.1.1", "5.5.5.5", "9.9.9.9", "7.7.7.7", "5.5.5.4",
               "5.5.5.5", "5.5.5.6", "5.5.5.7", "5.5.5.8", "5.5.5.9"]
    unit_points = points / len(ip_list)
    actual = json.loads(run("ip_check", *ip_list))
    actual_json[f'ip_check'] = actual
    
    with open("expected.json") as f:
        expected = json.load(f)["ip_check"]
    
    # compare length
    if abs(len(actual)-len(expected)) > 0:
        print(f"the number of input ips: {len(expected)}, but the number of output: {len(actual)}")
        
    # compare contents
    for i in range(len(expected)):
        try:
            actual_dict = actual[i]
            expected_dict = expected[i]
            
            if actual_dict['ip'] != expected_dict['ip']: # ip check
                print(f"expected ip {expected_dict['ip']}, but found {actual_dict['ip']}")
                points -= unit_points
            else:
                if actual_dict['int_ip'] != expected_dict['int_ip']: # int_ip check
                    print(f"ip: {expected_dict['ip']}, expected ip_int {expected_dict['int_ip']} but found {actual_dict['int_ip']}")
                    points -= unit_points
                else:
                    if actual_dict['region'] != expected_dict['region']: # region check
                        print(f"ip: {expected_dict['ip']}, expected region {expected_dict['region']} but found {actual_dict['region']}")
                        points -= unit_points
        except IndexError as e:
            print(f"missing: {expected[i]['ip']}")
            points -= unit_points
    
    ip_table = pd.read_csv("ip2location.csv")
    linear_search_time = []
    for i in range(10):
        start_time = time.time()
        for _ in range(len(ip_table)):
            pass
        linear_search_time.append((time.time() - start_time) * 1e3)
    
    avg_time_actual = np.mean([x['ms'] for x in actual[6:]])
    avg_time_linear = np.mean(linear_search_time)
    
    if avg_time_actual > avg_time_linear:
        print("(-10) Not enough optimized! It should be able to give better solution than naive linear search for consecutive ips")
        print(f"Average ip_check 'ms': {avg_time_actual}")
        print(f"Linear search time: {avg_time_linear}")
        points -= 10
    return max(points, 0)

@test(points=25)
def region():
    start_time = time.time()
    try:
        run("region", "server_log.zip", "temp.zip")
    except subprocess.TimeoutExpired:
        print("Execution time for sample should be less than 30 seconds")
        return 0

    elapsed_time = time.time() - start_time # check later since sort should be checked first.
    if elapsed_time > 30:
        print("Execution time for sample should be less than 30 seconds")
        return 0

    points = 0

    df = pd.read_csv("temp.zip")
    err = is_expected(len(df), "row_count")
    if err:
        print(err)
    else:
        points += 5

    ips = df["ip"]
    err = is_expected(str(ips.dtype), "ip_column_dtype")
    if err:
        print(err)
    else:
        points += 10

        for i in range(len(ips) - 1):
            if ips.iat[i] > ips.iat[i+1]:
                print("IPs not in ascending order")
                points -= 5
                break

    regions = dict(zip(df["ip"].values, df["region"].values))
    
    errors = []
    for ip, region in regions.items():
        assert isinstance(region, str)
        err = is_expected(region, f"region-for-ip-{ip}")
        if err:
            errors.append(err)
    if errors:
        print(errors[0])
    else:
        points += 10

    return points

@test(points=25)
def zipcode():
    points = 25;
    zname = "docs.zip"
    
    actual = run("zipcode", zname).strip().split("\n")
    actual_json['zipcode'] = actual
    
    # open expected
    with open('expected.json', 'r') as f:
        expected_json = json.load(f)
        expected = set(expected_json['zipcode'])
    
    # no duplicated check
    if len(actual) - len(set(actual)) > 0 :
        print("(-10) There are duplicated zip codes!")
        print("Duplicated zip codes and counts")
        
        # count zip codes
        wc = defaultdict(int)
        for zipcode in actual:
            wc[zipcode] += 1
            
        # show duplicated zip codes
        duplicated_count = 0
        print_threshold = 10
        for zipcode in wc:
            if wc[zipcode] > 1:
                duplicated_count += 1
                if duplicated_count <= print_threshold:
                    print(zipcode, f", count: {wc[zipcode]}")
        if duplicated_count > print_threshold:
            print(f"... [{duplicated_count-print_threshold}] more zip codes are duplicated.")
        points -= 10
    
    # missing values check
    actual = set(actual)
    weight = 25
    missed = set(expected).difference(set(actual))
    missed_count = len(missed)
    points -= missed_count / len(expected) * weight
    if missed_count > 0:
        print(f"Total {missed_count} zip codes are missed!")
        
    for pn in sorted(missed)[:10]:
        print(f"missed zip code: {pn}")
    
    if missed_count > 10:
        print(f"... [{missed_count-10}] more zip codes are missed.")
        
    points = max(0, points)  
    
    return points 

@test(points=25)
def geo():
    points = 0
    expected_shape_count = [74, 288, 18, 15, 27]

    for proj in (3035, 4036, 4144, 4248, 4555):
        proj = str(proj)
        out = proj + ".svg"
        if os.path.exists(out):
            os.remove(out)

        run("geo", proj, out)
        if os.path.exists(out):
            points += 1
        else:
            print(f"{out} not found")
            continue

        try:
            stats = svg_analyze(out)
        except Exception as e:
            print("ERROR ANALYZING "+out)
            print(e)
            continue

        points += 1

        if stats["colors"] < 3 or stats["colors"] > 5:
            print(f"the colors in {out} do not appear correct")
        else:
            points += 1

        expected = expected_shape_count.pop(0)
        actual = stats["paths"]

        if (expected-10 <= actual <= expected+10) or (expected*0.75 <= actual <= expected*1.25):
            points += 2
        else:
            print(f"expected about {expected} shapes in {out} but found {actual}")

    return points

########################################
# RUNNER
########################################

def main():
    global prog_name
    
    # import main.py (or other, if specified)
    prog_name = "main.py"
    if len(sys.argv) > 2:
        print("Usage: python3 test.py [prog_name]")
        sys.exit(1)
    elif len(sys.argv) == 2:
        prog_name = sys.argv[1]
        if not prog_name.endswith(".py"):
            prog_name += ".py"

    run_all_tests()

if __name__ == "__main__":
    main()
