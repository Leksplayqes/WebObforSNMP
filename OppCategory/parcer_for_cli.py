import json


def cli_to_category():
    with open("test") as file:
        data = file.read()
    x = data.split("\n")
    f = {}
    for com in x:
        if "category" in com:
            y = com.split()
            z = ' '.join(y[:y.index("<1-5>")])
            f[z] = y.count("<1-5>")
    with open("OppCategory.json", "r") as dev:
        oid = json.load(dev)
    oid["CliCategory"]["MASv1"] = f
    with open("OppCategory.json", "w") as block:
        json.dump(oid, block)
    return oid


# cli_to_category()
