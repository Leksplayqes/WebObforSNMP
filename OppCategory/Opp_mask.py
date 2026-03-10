from puresnmp.types import Integer

from Opp_mainSettings import client, set_oid_value, get_oid_value


async def mask_process_block(block, block_data, block_list):
    client_instance = client()
    for obj, (oid, depth) in block_data.items():
        x = 0
        if block == "MX100GCv1":
            base_oid = "1.3.6.1.4.1.5756.9.1.2.11.1.3.1.1.1.2"
            if oid == ".1.3.6.1.4.1.5756.9.1.2.11.1.3.3.2.1.4.":
                await set_oid_value(client_instance, f"{base_oid}.{block_list[block]}.1", Integer(3))
                await set_oid_value(client_instance, f"{oid}{block_list[block]}.1", Integer(x))
            elif oid == ".1.3.6.1.4.1.5756.9.1.2.11.1.3.4.2.1.4.":
                await set_oid_value(client_instance, f"{base_oid}.{block_list[block]}.2", Integer(5))
                await set_oid_value(client_instance, f"{oid}{block_list[block]}.2", Integer(x))
            elif oid in (".1.3.6.1.4.1.5756.9.1.2.11.1.3.5.2.1.4.",
                         ".1.3.6.1.4.1.5756.9.1.2.11.1.3.6.2.1.4.",
                         ".1.3.6.1.4.1.5756.9.1.2.11.1.3.7.2.1.4."):
                await set_oid_value(client_instance, f"{base_oid}.{block_list[block]}.3", Integer(1))
                await set_oid_value(client_instance, f"{oid}{block_list[block]}.3{'.1' * (depth - 2)}", Integer(0))
            else:
                await set_oid_value(client_instance, f"{oid}{block_list[block]}{'.1' * (depth - 1)}", Integer(x))
        if block == "TP510Gv1":
            base_oid = "1.3.6.1.4.1.5756.9.1.2.15.1.2.1.1.1.2"
            if oid == ".1.3.6.1.4.1.5756.9.1.2.15.1.2.3.2.1.4.":
                await set_oid_value(client_instance, f"{base_oid}.{block_list[block]}.1", Integer(3))
                await set_oid_value(client_instance, f"{oid}{block_list[block]}.1", Integer(x))
            elif oid == ".1.3.6.1.4.1.5756.9.1.2.15.1.2.4.2.1.4.":
                await set_oid_value(client_instance, f"{base_oid}.{block_list[block]}.2", Integer(5))
                await set_oid_value(client_instance, f"{oid}{block_list[block]}.2", Integer(x))
            elif oid in (".1.3.6.1.4.1.5756.9.1.2.15.1.2.5.2.1.4.",
                         ".1.3.6.1.4.1.5756.9.1.2.15.1.2.6.2.1.4.",
                         ".1.3.6.1.4.1.5756.9.1.2.15.1.2.7.2.1.4."):
                await set_oid_value(client_instance, f"{base_oid}.{block_list[block]}.3", Integer(1))
                await set_oid_value(client_instance, f"{oid}{block_list[block]}.3{'.1' * (depth - 2)}", Integer(x))
            else:
                await set_oid_value(client_instance, f"{oid}{block_list[block]}{'.1' * (depth - 1)}", Integer(x))
        else:
            await set_oid_value(client_instance, f"{oid}{block_list[block]}{'.1' * (depth - 1)}", Integer(x))


async def mask_reading_block(block, block_data, block_list):
    client_instance = client()
    all_values = {}
    for obj, (oid, depth) in block_data.items():
        if block == "MX100GCv1":
            if oid == ".1.3.6.1.4.1.5756.9.1.2.11.1.3.3.2.1.4.":
                all_values[oid] = await get_oid_value(client_instance, f"{oid}{block_list[block]}.1")
            elif oid == ".1.3.6.1.4.1.5756.9.1.2.11.1.3.4.2.1.4.":
                all_values[oid] = await get_oid_value(client_instance, f"{oid}{block_list[block]}.2")
            elif oid in (".1.3.6.1.4.1.5756.9.1.2.11.1.3.5.2.1.4.",
                         ".1.3.6.1.4.1.5756.9.1.2.11.1.3.6.2.1.4.",
                         ".1.3.6.1.4.1.5756.9.1.2.11.1.3.7.2.1.4."):
                all_values[oid] = await get_oid_value(client_instance, f"{oid}{block_list[block]}.3{'.1' * (depth - 2)}")
            else:
                all_values[oid] = await get_oid_value(client_instance, f"{oid}{block_list[block]}{'.1' * (depth - 1)}")
        if block == "TP510Gv1":
            if oid == ".1.3.6.1.4.1.5756.9.1.2.15.1.2.3.2.1.4.":
                all_values[oid] = await get_oid_value(client_instance, f"{oid}{block_list[block]}.1")
            elif oid == ".1.3.6.1.4.1.5756.9.1.2.15.1.2.4.2.1.4.":
                all_values[oid] = await get_oid_value(client_instance, f"{oid}{block_list[block]}.2")
            elif oid in (".1.3.6.1.4.1.5756.9.1.2.15.1.2.5.2.1.4.",
                         ".1.3.6.1.4.1.5756.9.1.2.15.1.2.6.2.1.4.",
                         ".1.3.6.1.4.1.5756.9.1.2.15.1.2.7.2.1.4."):
                all_values[oid] = await get_oid_value(client_instance, f"{oid}{block_list[block]}.3{'.1' * (depth - 2)}")
            else:
                all_values[oid] = await get_oid_value(client_instance, f"{oid}{block_list[block]}{'.1' * (depth - 1)}")
        else:
            all_values[oid] = await get_oid_value(client_instance, f"{oid}{block_list[block]}{'.1' * (depth - 1)}")
    return all_values
