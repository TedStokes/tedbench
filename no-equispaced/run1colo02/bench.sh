#!/bin/bash
: > build.log
: > stdout.log
: > stderr.log
: > time.log

cd ~/master_nektar++/build
git fetch --all
git checkout ted/master
rm CMakeCache.txt
cmake -DNEKTAR_USE_HDF5=ON -DNEKTAR_USE_MPI=ON -DNEKTAR_USE_VTK=ON .. &>> ~/tedbench/no-equispaced/run1colo02/build.log
make install -j100 &>> ~/tedbench/no-equispaced/run1colo02/build.log
cd ~/third_nektar++/build
git fetch --all
git checkout ted/feature/geomfactors-refactor
rm CMakeCache.txt
cmake -DNEKTAR_USE_HDF5=ON -DNEKTAR_USE_MPI=ON -DNEKTAR_USE_VTK=ON .. &>> ~/tedbench/no-equispaced/run1colo02/build.log
make install -j100 &>> ~/tedbench/no-equispaced/run1colo02/build.log

cd ~/tedbench/no-equispaced/run1colo02
for s in 2 10 13 15 16 18 19
do
    cp ~/tedbench/cube_tet_template.geo cube_tet_$s.geo
    sed -i s/size_var/$s/g cube_tet_$s.geo
    gmsh -3 cube_tet_$s.geo >/dev/null
    rm cube_tet_$s.geo
    ~/master_nektar++/build/dist/bin/NekMesh cube_tet_$s.msh cube_tet_$s.xml -f
    rm cube_tet_$s.msh
    let num=$s*$s*$s*6
    echo $s "*" $s "*" $s "* 6 = " $num " tets"

    echo "master"
    /bin/time -v -o tmp_time.log \
      ~/master_nektar++/build/dist/bin/FieldConvert cube_tet_$s.xml cube_tet_$s.vtu -f -v \
      > >(tee -a "stdout.log") \
      2> >(tee -a "stderr.log" >&2) \
      | grep -e "InputXml CPU Time: " -e "OutputVtk CPU Time: " -e "ERROR:"
    cat tmp_time.log >> time.log
    grep -e "Maximum resident set size" tmp_time.log
    rm cube_tet_$s.vtu
    echo ""

    echo "feature/geomfactors-refactor"
    /bin/time -v -o tmp_time.log \
      ~/third_nektar++/build/dist/bin/FieldConvert cube_tet_$s.xml cube_tet_$s.vtu -f -v \
      > >(tee -a "stdout.log") \
      2> >(tee -a "stderr.log" >&2) \
      | grep -e "InputXml CPU Time: " -e "OutputVtk CPU Time: " -e "ERROR:"
    cat tmp_time.log >> time.log
    grep -e "Maximum resident set size" tmp_time.log
    rm cube_tet_$s.vtu
    echo ""

    echo "master no-equispaced"
    /bin/time -v -o tmp_time.log \
      ~/master_nektar++/build/dist/bin/FieldConvert cube_tet_$s.xml cube_tet_$s.vtu --no-equispaced -f -v \
      > >(tee -a "stdout.log") \
      2> >(tee -a "stderr.log" >&2) \
      | grep -e "InputXml CPU Time: " -e "OutputVtk CPU Time: " -e "ERROR:"
    cat tmp_time.log >> time.log
    grep -e "Maximum resident set size" tmp_time.log
    rm cube_tet_$s.vtu
    echo ""

    echo "feature/geomfactors-refactor no-equispaced"
    /bin/time -v -o tmp_time.log \
      ~/third_nektar++/build/dist/bin/FieldConvert cube_tet_$s.xml cube_tet_$s.vtu --no-equispaced -f -v \
      > >(tee -a "stdout.log") \
      2> >(tee -a "stderr.log" >&2) \
      | grep -e "InputXml CPU Time: " -e "OutputVtk CPU Time: " -e "ERROR:"
    cat tmp_time.log >> time.log
    grep -e "Maximum resident set size" tmp_time.log
    rm cube_tet_$s.vtu
    echo ""

    rm cube_tet_$s.xml
    rm tmp_time.log
done