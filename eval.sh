echo -e "\nEvaluating the Speak Test Set"
python eval.py ./examples/librispeech/models/ctc_models/$1/$2 ~/awni_speech/data/speak_test_data/speak_test.json --save ./predictions/$1-$2_speak_test_predictions.json
echo -e "\nEvaluating Dustin Clean Testset"
python eval.py ./examples/librispeech/models/ctc_models/$1/$2 ~/awni_speech/data/dustin_test_data/20191202_clean/drz_test.json --save ./predictions/$1-$2_1202_predictions.json
echo -e "\nEvaluating the Dustin Noisy Testset"
python eval.py ./examples/librispeech/models/ctc_models/$1/$2 ~/awni_speech/data/dustin_test_data/20191118_plane/simple/drz_test.json --save ./predictions/$1-$2_1118-simple_predictions.json
echo -e "\nEvaluating lib-ted-cv Testset"
python eval.py ./examples/librispeech/models/ctc_models/$1/$2 ~/awni_speech/data/lib-ted-cv/test_lib-ted-cv.json --save ./predictions/$1-$2_test-lib-ted-cv_predictions.json
