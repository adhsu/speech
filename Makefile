
all: warp

warp:
	git clone https://github.com/awni/warp-ctc.git libs/warp-ctc 
	cd libs/warp-ctc; mkdir build; cd build; cmake ../ && make; \
		cd ../pytorch_binding; python build.py


