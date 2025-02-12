import json
import tempfile
from urllib.request import urlopen, urlretrieve

from boutiques.logger import print_info, print_warning, raise_error
from boutiques.publisher import Publisher
from boutiques.puller import Puller
from boutiques.util.utils import loadJson
from boutiques.zenodoHelper import ZenodoError, ZenodoHelper


class DeprecateError(Exception):
    pass


def deprecate(
    zenodo_id,
    by_zenodo_id=None,
    sandbox=False,
    verbose=False,
    zenodo_token=None,
    download_function=urlretrieve,
):

    # Get the descriptor and Zenodo id
    puller = Puller([zenodo_id], verbose=verbose, sandbox=sandbox)
    descriptor_fname = puller.pull()[0]
    descriptor_json = loadJson(descriptor_fname, sandbox=sandbox, verbose=verbose)

    # Return if tool is already deprecated
    deprecated = descriptor_json.get("deprecated-by-doi")
    if deprecated is not None:
        if isinstance(deprecated, str):
            print_info(f"Tool {zenodo_id} is already deprecated by {deprecated} ")
        if by_zenodo_id is not None:
            prompt = (
                "Tool {} will be deprecated by {}, "
                "this cannot be undone. Are you sure? (Y/n) "
            ).format(zenodo_id, by_zenodo_id)
            ret = input(prompt)
            if ret.upper() != "Y":
                return
        else:
            print_warning(f"Tool {zenodo_id} is already deprecated")
            return
    # Set record id and Zenodo id
    zhelper = ZenodoHelper(sandbox=sandbox, no_int=True, verbose=verbose)
    zid = zhelper.get_zid_from_filename(descriptor_fname)
    record_id = zhelper.get_record_id_from_zid(zid)

    # Return if tool has a newer version
    record = zhelper.zenodo_get_record(record_id)
    if not record["metadata"]["relations"]["version"][0]["is_last"]:
        new_version = record["metadata"]["relations"]["version"][0]["last_child"][
            "pid_value"
        ]
        raise_error(
            DeprecateError,
            "Tool {} has a newer version "
            "(zenodo.{}), it cannot be deprecated.".format(zenodo_id, new_version),
        )
        return

    # Add deprecated property
    if by_zenodo_id is None:
        descriptor_json["deprecated-by-doi"] = True
    else:
        # Check that by_zenodo_id exists
        by_record_id = zhelper.get_record_id_from_zid(by_zenodo_id)
        if zhelper.record_exists(by_record_id) is False:
            raise_error(DeprecateError, f"Tool does not exist: {by_zenodo_id}")
        # Assign deprecated-by property
        by_doi_id = zhelper.get_doi_from_zid(by_zenodo_id)
        descriptor_json["deprecated-by-doi"] = by_doi_id

    # Add doi to descriptor (mandatory for update)
    if descriptor_json.get("doi") is None:
        descriptor_json["doi"] = zhelper.get_doi_from_zid(zid)

    # Save descriptor in temp file
    tmp = tempfile.NamedTemporaryFile(delete=False, mode="w", suffix=".json")
    content = json.dumps(descriptor_json, indent=4, sort_keys=True)
    tmp.write(content)
    tmp.close()

    # Publish updated descriptor
    publisher = Publisher(
        tmp.name,
        zenodo_token,
        replace=True,
        sandbox=sandbox,
        no_int=True,
        id="zenodo." + zid,
        verbose=verbose,
    )
    return publisher.publish()
