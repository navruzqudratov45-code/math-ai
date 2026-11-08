import unittest

import sympy as sp

from math_engine import EngineInputError, compute


class PlaneGeometryTests(unittest.TestCase):
    def test_triangle_heron_area_and_diagram(self):
        result = compute({"problem": "Tomonlari 3, 4, 5 bo‘lgan uchburchak yuzini toping"})
        self.assertEqual(result["result"], "6")
        self.assertEqual(result["diagram"]["kind"], "triangle")
        self.assertIn("Geron", " ".join(result["steps"]))

    def test_triangle_perimeter(self):
        result = compute({"problem": "Triangle sides 3, 4, 5: find perimeter"})
        self.assertEqual(result["result"], "12")

    def test_triangle_base_height(self):
        result = compute({"problem": "Triangle base 10, height 6, calculate area"})
        self.assertEqual(result["result"], "30")

    def test_triangle_interior_angle(self):
        result = compute({"problem": "A triangle has angles 50 and 60 degrees. Find the third angle"})
        self.assertEqual(result["result"], "70")

    def test_pythagorean_hypotenuse(self):
        result = compute({"problem": "Right triangle has legs 3 and 4; find hypotenuse"})
        self.assertEqual(result["result"], "5")

    def test_pythagorean_area(self):
        result = compute({"problem": "Right triangle legs 3 and 4; find area"})
        self.assertEqual(result["result"], "6")

    def test_circle_area_and_circumference(self):
        area = compute({"problem": "Radiusi 7 cm bo‘lgan aylananing yuzini toping"})
        circumference = compute({"problem": "Circle radius 7: find circumference"})
        self.assertEqual(area["result"], "49*pi")
        self.assertEqual(circumference["result"], "14*pi")
        self.assertEqual(area["diagram"]["kind"], "circle")

    def test_circle_diameter_from_radius(self):
        result = compute({"problem": "Circle radius 7, find diameter"})
        self.assertEqual(result["result"], "14")

    def test_rectangle_area_and_perimeter(self):
        area = compute({"problem": "Rectangle length 8, width 3; find area"})
        perimeter = compute({"problem": "Rectangle length 8, width 3; find perimeter"})
        self.assertEqual(area["result"], "24")
        self.assertEqual(perimeter["result"], "22")

    def test_trapezoid_area(self):
        result = compute({"problem": "Trapezoid bases 5 and 9, height 4; find area"})
        self.assertEqual(result["result"], "28")

    def test_parallelogram_area(self):
        result = compute({"problem": "Parallelogram base 10, height 6: find area"})
        self.assertEqual(result["result"], "60")

    def test_rhombus_area_from_diagonals(self):
        result = compute({"problem": "Rhombus diagonals 6 and 8: find area"})
        self.assertEqual(result["result"], "24")

    def test_regular_hexagon_area(self):
        result = compute({"problem": "Find the area of a regular hexagon with side 2"})
        self.assertEqual(sp.simplify(sp.sympify(result["result"]) - 6 * sp.sqrt(3)), 0)

    def test_regular_polygon_perimeter(self):
        result = compute({"problem": "Perimeter of a regular hexagon with side 2"})
        self.assertEqual(result["result"], "12")

    def test_similarity_scale_factor(self):
        result = compute({"problem": "Similar triangles scale factor 2, corresponding side 4; find new side"})
        self.assertEqual(result["result"], "8")

    def test_triangle_similarity_check(self):
        result = compute({"problem": "Are triangles with sides 3, 4, 5 and 6, 8, 10 similar?"})
        self.assertEqual(result["result"], "True")

    def test_triangle_congruence_check(self):
        result = compute({"problem": "Are triangles with sides 3, 4, 5 and 3, 4, 5 congruent?"})
        self.assertEqual(result["result"], "True")

    def test_triangle_rejects_invalid_sides(self):
        with self.assertRaises(EngineInputError):
            compute({"problem": "Triangle sides 1, 2, 8: find area"})


class SolidGeometryTests(unittest.TestCase):
    def test_cube_volume_and_surface(self):
        volume = compute({"problem": "Cube side 3: find volume"})
        surface = compute({"problem": "Cube side 3: find surface area"})
        self.assertEqual(volume["result"], "27")
        self.assertEqual(surface["result"], "54")

    def test_cuboid_volume(self):
        result = compute({"problem": "Cuboid length 2, width 3, height 4: find volume"})
        self.assertEqual(result["result"], "24")

    def test_cylinder_volume(self):
        result = compute({"problem": "Cylinder radius 2, height 5: find volume"})
        self.assertEqual(result["result"], "20*pi")

    def test_cone_volume(self):
        result = compute({"problem": "Cone radius 3, height 4: find volume"})
        self.assertEqual(result["result"], "12*pi")

    def test_sphere_surface_area(self):
        result = compute({"problem": "Sphere radius 3: find surface area"})
        self.assertEqual(result["result"], "36*pi")

    def test_sphere_volume(self):
        result = compute({"problem": "Sphere radius 3: find volume"})
        self.assertEqual(result["result"], "36*pi")

    def test_cone_slant_height(self):
        result = compute({"problem": "Cone radius 3, height 4: find side length"})
        self.assertEqual(result["result"], "5")

    def test_cylinder_surface_area(self):
        result = compute({"problem": "Cylinder radius 2, height 5: find surface area"})
        self.assertEqual(result["result"], "28*pi")

    def test_pyramid_surface_area(self):
        result = compute({"problem": "Pyramid base area 16, height 6, base perimeter 16, slant height 5: find surface area"})
        self.assertEqual(result["result"], "56")

    def test_prism_volume(self):
        result = compute({"problem": "Prism base area 12, height 5: find volume"})
        self.assertEqual(result["result"], "60")

    def test_pyramid_volume(self):
        result = compute({"problem": "Pyramid base area 18, height 6: find volume"})
        self.assertEqual(result["result"], "36")


class CoordinateGeometryTests(unittest.TestCase):
    def test_coordinate_distance(self):
        result = compute({"problem": "Find distance between A(1, 2) and B(4, 6)"})
        self.assertEqual(result["result"], "5")
        self.assertEqual(result["diagram"]["kind"], "coordinates")

    def test_coordinate_midpoint(self):
        result = compute({"problem": "Find midpoint of A(1, 2), B(4, 6)"})
        self.assertEqual(result["result"], "(5/2, 4)")

    def test_coordinate_slope(self):
        result = compute({"problem": "Find slope of line through (1, 2) and (4, 6)"})
        self.assertEqual(result["result"], "4/3")

    def test_coordinate_line_equation(self):
        result = compute({"problem": "Find equation of the line through A(1, 2) and B(4, 6)"})
        self.assertIn("4*x/3 + 2/3", result["result"])

    def test_coordinate_triangle_area(self):
        result = compute({"problem": "Find area of triangle with coordinates A(0, 0), B(4, 0), C(0, 3)"})
        self.assertEqual(result["result"], "6")


if __name__ == "__main__":
    unittest.main()
