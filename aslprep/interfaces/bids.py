"""Adapted interfaces from Niworkflows."""

from json import loads

from bids.layout import Config
from nipype.interfaces.base import (
    BaseInterfaceInputSpec,
    OutputMultiObject,
    SimpleInterface,
    Str,
    TraitedSpec,
    traits,
)
from niworkflows.interfaces.bids import DerivativesDataSink as BaseDerivativesDataSink

from aslprep import config
from aslprep.data import load as load_data

# NOTE: Modified for aslprep's purposes
aslprep_spec = loads(load_data.readable('aslprep_bids_config.json').read_text())
bids_config = Config.load('bids')
deriv_config = Config.load('derivatives')

aslprep_entities = {v['name']: v['pattern'] for v in aslprep_spec['entities']}
merged_entities = {**bids_config.entities, **deriv_config.entities}
merged_entities = {k: v.pattern for k, v in merged_entities.items()}
merged_entities = {**merged_entities, **aslprep_entities}
merged_entities = [{'name': k, 'pattern': v} for k, v in merged_entities.items()]
config_entities = frozenset({e['name'] for e in merged_entities})


class _BIDSDataGrabberInputSpec(BaseInterfaceInputSpec):
    subject_data = traits.Dict(Str, traits.Any)
    subject_id = Str()


class _BIDSDataGrabberOutputSpec(TraitedSpec):
    out_dict = traits.Dict(desc='output data structure')
    fmap = OutputMultiObject(desc='output fieldmaps')
    bold = OutputMultiObject(desc='output functional images')
    sbref = OutputMultiObject(desc='output sbrefs')
    t1w = OutputMultiObject(desc='output T1w images')
    roi = OutputMultiObject(desc='output ROI images')
    t2w = OutputMultiObject(desc='output T2w images')
    flair = OutputMultiObject(desc='output FLAIR images')
    pet = OutputMultiObject(desc='output PET images')
    dwi = OutputMultiObject(desc='output DWI images')
    asl = OutputMultiObject(desc='output ASL images')


class BIDSDataGrabber(SimpleInterface):
    """Collect files from a BIDS directory structure.

    .. testsetup::

        >>> data_dir_canary()

    >>> bids_src = BIDSDataGrabber(anat_only=False)
    >>> bids_src.inputs.subject_data = bids_collect_data(
    ...     str(datadir / 'ds114'), '01', bids_validate=False)[0]
    >>> bids_src.inputs.subject_id = '01'
    >>> res = bids_src.run()
    >>> res.outputs.t1w  # doctest: +ELLIPSIS +NORMALIZE_WHITESPACE
    ['.../ds114/sub-01/ses-retest/anat/sub-01_ses-retest_T1w.nii.gz',
     '.../ds114/sub-01/ses-test/anat/sub-01_ses-test_T1w.nii.gz']

    """

    input_spec = _BIDSDataGrabberInputSpec
    output_spec = _BIDSDataGrabberOutputSpec
    _require_funcs = True

    def __init__(self, *args, **kwargs):
        anat_only = kwargs.pop('anat_only')
        anat_derivatives = kwargs.pop('anat_derivatives', None)
        super().__init__(*args, **kwargs)
        if anat_only is not None:
            self._require_funcs = not anat_only
        self._require_t1w = anat_derivatives is None

    def _run_interface(self, runtime):
        bids_dict = self.inputs.subject_data

        self._results['out_dict'] = bids_dict
        self._results.update(bids_dict)

        if self._require_t1w and not bids_dict['t1w']:
            raise FileNotFoundError(
                f'No T1w images found for subject sub-{self.inputs.subject_id}'
            )

        if self._require_funcs and not bids_dict['asl']:
            raise FileNotFoundError(
                f'No ASL images found for subject sub-{self.inputs.subject_id}'
            )

        for imtype in ['bold', 't2w', 'flair', 'fmap', 'sbref', 'roi', 'pet', 'asl']:
            if not bids_dict.get(imtype):
                config.loggers.interface.info(
                    'No "%s" images found for sub-%s', imtype, self.inputs.subject_id
                )

        return runtime


class DerivativesDataSink(BaseDerivativesDataSink):
    """Store derivative files.

    A child class of the niworkflows DerivativesDataSink, using aslprep's configuration files.
    """

    out_path_base = ''
    _allowed_entities = set(config_entities)
    _config_entities = config_entities
    _config_entities_dict = merged_entities
    _file_patterns = aslprep_spec['default_path_patterns']


class OverrideDerivativesDataSink:
    """A context manager for temporarily overriding the definition of DerivativesDataSink.

    Parameters
    ----------
    None

    Attributes
    ----------
    original_class (type): The original class that is replaced during the override.

    Methods
    -------
    __init__()
        Initialize the context manager.
    __enter__()
        Enters the context manager and performs the class override.
    __exit__(exc_type, exc_value, traceback)
        Exits the context manager and restores the original class definition.
    """

    def __init__(self, module):
        """Initialize the context manager with the target module.

        Parameters
        -----------
        module
            The module where SomeClass should be overridden.
        """
        self.module = module

    def __enter__(self):
        """Enter the context manager and perform the class override.

        Returns
        -------
        OverrideConfoundsDerivativesDataSink
            The instance of the context manager.
        """
        # Save the original class
        self.original_class = self.module.DerivativesDataSink
        # Replace SomeClass with YourOwnClass
        self.module.DerivativesDataSink = DerivativesDataSink
        return self

    def __exit__(self, exc_type, exc_value, traceback):  # noqa: U100
        """Exit the context manager and restore the original class definition.

        Parameters
        ----------
        exc_type : type
            The type of the exception (if an exception occurred).
        exc_value : Exception
            The exception instance (if an exception occurred).
        traceback : traceback
            The traceback information (if an exception occurred).

        Returns
        -------
        None
        """
        # Restore the original class
        self.module.DerivativesDataSink = self.original_class


class FunctionOverrideContext:
    """Override a function in imported code with a context manager.

    Even though this class is *currently* unused, I'm keeping it around for when I need to override
    prepare_timing_parameters once fMRIPrep's init_bold_surf_wf is usable
    (i.e., once the DerivativesDataSink import is moved out of the function).

    Here's how it worked before:

    def _fake_params(metadata):  # noqa: U100
        return {"SliceTimingCorrected": False}

    # init_bold_surf_wf uses prepare_timing_parameters, which uses the config object.
    # The uninitialized fMRIPrep config will have config.workflow.ignore set to None
    # instead of a list, which will raise an error.
    with FunctionOverrideContext(resampling, "prepare_timing_parameters", _fake_params):
        asl_surf_wf = resampling.init_bold_surf_wf(
            mem_gb=mem_gb["resampled"],
            metadata=metadata,
            surface_spaces=freesurfer_spaces,
            medial_surface_nan=config.workflow.medial_surface_nan,
            output_dir=config.execution.aslprep_dir,
            name="asl_surf_wf",
        )
    """

    def __init__(self, module, function_name, new_function):
        self.module = module
        self.function_name = function_name
        self.new_function = new_function
        self.original_function = None

    def __enter__(self):
        """Enter the context manager and perform the function override.

        Returns
        -------
        FunctionOverrideContext
            The instance of the context manager.
        """
        self.original_function = getattr(self.module, self.function_name)
        setattr(self.module, self.function_name, self.new_function)

    def __exit__(self, exc_type, exc_value, traceback):  # noqa: U100
        """Exit the context manager and restore the original function definition.

        Parameters
        ----------
        exc_type : type
            The type of the exception (if an exception occurred).
        exc_value : Exception
            The exception instance (if an exception occurred).
        traceback : traceback
            The traceback information (if an exception occurred).

        Returns
        -------
        None
        """
        setattr(self.module, self.function_name, self.original_function)
