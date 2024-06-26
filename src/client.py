import os

import flwr as fl
import tensorflow as tf
from fastapi import FastAPI, File, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sklearn.model_selection import train_test_split

import utils.ipfs as verify
from config import *
from dataset.config import *
from FedML.FLclient import CifarClient
from services.bc_client_service import BlockchainService
from utils import dataset, utils

# Parse command line argument `partition`
# parser = argparse.ArgumentParser(description="Flower")
# parser.add_argument("--partition", type=int, choices=range(0, 5), required=True)
# args = parser.parse_args()
# client_id = args.partition

CLIENT_ID = None
app = FastAPI()
blockchainService = BlockchainService()


print(tf.config.list_physical_devices("GPU"))


class FLlaunch:
    def start(self, dataset_name, session):
        dataset.change_dataset(dataset_name)
        print(dataset.get_dataset_path())
        listen_and_participate(CLIENT_ID, session)


def handle_launch_FL_session(
    model,
    x_train,
    y_train,
    x_test,
    y_test,
    x_val,
    y_val,
    client_id,
    client_address,
    session,
):
    """
    handles smart contract's addStrategy event by starting flwr client
    """

    record = utils.record_performance()

    fl.client.start_client(
        server_address=FLWR_SERVER + ":" + FLWR_PORT,
        client=CifarClient(
            model,
            x_train,
            y_train,
            x_test,
            y_test,
            x_val,
            y_val,
            client_id,
            client_address,
        ).to_client(),
        grpc_max_message_length=1024 * 1024 * 1024,
    )

    utils.plot_performance_report(
        record, f"./results/Session-{session}/performance-client_{CLIENT_ID + 1}.png"
    )


@app.post("/participateFL")
def listen_and_participate(client_id: int, session: int):
    client_address = blockchainService.getAddress(client_id)
    # If client_id is odd number, the program will use GPU to train the model,
    # else CPU will train the model

    x_train, y_train = dataset.get_dataset(df=dataset.load_dataset_full(client_id))
    x_val, y_val = dataset.get_dataset(df=dataset.load_dataset_validate())

    if len(x_val) > 0.1 * len(x_train):
        _, x_val, _, y_val = train_test_split(
            x_val, y_val, test_size=0.1 * len(x_train) / len(x_val), stratify=y_val
        )

    x_test, y_test = dataset.get_dataset(df=dataset.load_dataset_test())
    _, x_test, _, y_test = train_test_split(
        x_test, y_test, test_size=0.2, stratify=y_test
    )

    model = utils.get_model(inshape=x_train.shape[1])
    handle_launch_FL_session(
        model,
        x_train,
        y_train,
        x_test,
        y_test,
        x_val,
        y_val,
        client_id,
        client_address,
        session,
    )


@app.get("/getContributions")
def getContributions(client_id: int):
    client_address = client_address = blockchainService.getAddress(client_id)
    contributions = BlockchainService.getContributions(client_address)
    # Conver Python list to JSON
    json_compatible_item_data = jsonable_encoder(contributions)
    return JSONResponse(content=json_compatible_item_data)


@app.get("/")
def testFAST(client_id: int):
    global CLIENT_ID
    CLIENT_ID = client_id
    client_address = blockchainService.getAddress(client_id)
    return ("Hello from client add: ", client_address)


@app.get("/getConfusionMaxtrix")
def getConfusionMaxtrixAfterFL():
    x_test, y_test = dataset.get_dataset(df=dataset.load_dataset_test())
    model = utils.get_model(inshape=x_test.shape[1])

    # latest_weights = verify.load_last_global_model_weights_from_localDB('./save-weights/Global-weights')
    latest_weights = verify.load_last_global_model_weights_from_IPFS()
    model.set_weights(latest_weights)
    verify.plot_confussion_matrix(model, x_test, y_test)
