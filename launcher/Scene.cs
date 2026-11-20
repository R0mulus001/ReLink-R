using System.Globalization;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Shapes;

namespace ReLink;

/// (ReLink-R: the violet night and the sword, below) The sky and the hills behind the window, upstream. They follow the player's clock, as the game's own day does: night, dawn, day and
/// dusk, with the sun or the moon as high as the hour puts it. The top of the sky stays dark at every hour: the title is read
/// there. (RELINK_HOUR=13.5 sets the hour, for tests)
static class Scene
{
    readonly record struct Key(double Hour, Color Top, Color Low);

    static Color C(string hex) => (Color)ColorConverter.ConvertFromString("#" + hex);

    static readonly Key[] Keys =
    {
        new(0, C("0A1424"), C("16303F")),
        new(4.75, C("0A1424"), C("16303F")),
        new(6.25, C("26375A"), C("D49A6A")),   // dawn
        new(8.5, C("235A8E"), C("9CCBD9")),    // day
        new(16.5, C("235A8E"), C("9CCBD9")),
        new(18.5, C("2A2F57"), C("DA8A52")),   // dusk
        new(20.25, C("0A1424"), C("16303F")),
        new(24, C("0A1424"), C("16303F")),
    };

    public static double Hour()
    {
        if (Environment.GetEnvironmentVariable("RELINK_HOUR") is { Length: > 0 } forced &&
            double.TryParse(forced, NumberStyles.Float, CultureInfo.InvariantCulture, out var h))
            return Math.Clamp(h, 0, 23.99);
        var now = DateTime.Now;
        return now.Hour + now.Minute / 60.0;
    }

    static Color Mix(Color a, Color b, double t) => Color.FromRgb(
        (byte)(a.R + (b.R - a.R) * t), (byte)(a.G + (b.G - a.G) * t), (byte)(a.B + (b.B - a.B) * t));

    static (Color Top, Color Low) Sky(double hour)
    {
        for (var i = 1; i < Keys.Length; i++)
            if (hour <= Keys[i].Hour)
            {
                var (a, b) = (Keys[i - 1], Keys[i]);
                var t = b.Hour > a.Hour ? (hour - a.Hour) / (b.Hour - a.Hour) : 0;
                return (Mix(a.Top, b.Top, t), Mix(a.Low, b.Low, t));
            }
        return (Keys[0].Top, Keys[0].Low);
    }

    /// (ReLink-R) The violet night behind the window at every hour: stars twinkling, a violet light, and the sword standing in its
    /// stone pedestal, where the sun or the moon was. The hour still sets how much of the light there is, a little
    public static void Draw(Canvas canvas, double w, double h, double hour)
    {
        canvas.Children.Clear();
        var day = hour > 6.5 && hour < 18.5 ? 1.0 : 0.0;
        var sky = new LinearGradientBrush { StartPoint = new(0, 0), EndPoint = new(0, 1) };
        sky.GradientStops.Add(new GradientStop(C("12102A"), 0));
        sky.GradientStops.Add(new GradientStop(Mix(C("1E1A4A"), C("2A2366"), day * 0.4), 0.38));
        sky.GradientStops.Add(new GradientStop(C("161335"), 1));
        canvas.Children.Add(new Rectangle { Width = w, Height = h, Fill = sky });

        const double x = 719, slot = 208;   // (ReLink-R: the sword over Play, on its axis: Play is 210 wide, 20 from the right of the 844 sky, 18 from its bottom; the pedestal's step, 208 wide, ends 12 above it)
        var halo = new RadialGradientBrush { GradientOrigin = new(0.5, 0.5), Center = new(0.5, 0.5), RadiusX = 0.5, RadiusY = 0.5 };
        halo.GradientStops.Add(new GradientStop(Color.FromArgb(0x70, 0x5A, 0x48, 0xD8), 0));
        halo.GradientStops.Add(new GradientStop(Color.FromArgb(0x00, 0x5A, 0x48, 0xD8), 1));
        var glow = new Ellipse { Width = 520, Height = 420, Fill = halo };
        Canvas.SetLeft(glow, x - 260);
        Canvas.SetTop(glow, slot - 260);
        canvas.Children.Add(glow);

        var rnd = new Random(1998);
        for (var i = 0; i < 70; i++)
        {
            var size = 1 + rnd.NextDouble() * 1.6;
            var gold = rnd.NextDouble() < 0.22;
            var star = new Ellipse { Width = size, Height = size, Fill = new SolidColorBrush(gold ? C("F6E3A6") : C("DCD6FF")), Opacity = 0.3 + rnd.NextDouble() * 0.6 };
            Canvas.SetLeft(star, rnd.NextDouble() * w);
            Canvas.SetTop(star, 6 + rnd.NextDouble() * 260);
            canvas.Children.Add(star);
            var twinkle = new System.Windows.Media.Animation.DoubleAnimation(star.Opacity, 0.12, TimeSpan.FromSeconds(1.4 + rnd.NextDouble() * 2.4))
            {
                AutoReverse = true, RepeatBehavior = System.Windows.Media.Animation.RepeatBehavior.Forever,
                BeginTime = TimeSpan.FromSeconds(rnd.NextDouble() * 3),
            };
            star.BeginAnimation(UIElement.OpacityProperty, twinkle);
        }

        // the light behind the blade
        var light = new RadialGradientBrush();
        light.GradientStops.Add(new GradientStop(Color.FromArgb(0x55, 0xF6, 0xE3, 0xA6), 0));
        light.GradientStops.Add(new GradientStop(Color.FromArgb(0x00, 0xF6, 0xE3, 0xA6), 1));
        var lit = new Ellipse { Width = 200, Height = 200, Fill = light };
        Canvas.SetLeft(lit, x - 100);
        Canvas.SetTop(lit, slot - 150);
        canvas.Children.Add(lit);

        // the pedestal: a step with a gold edge, a stone block wider at its foot, its top with a gold rim and the slot
        Hill(canvas, $"M{x - 104},{slot + 60} L{x + 104},{slot + 60} L{x + 104},{slot + 76} L{x - 104},{slot + 76} Z", C("2A2658"));
        Hill(canvas, $"M{x - 104},{slot + 60} L{x + 104},{slot + 60} L{x + 104},{slot + 62.5} L{x - 104},{slot + 62.5} Z", C("E2BE5A"));
        var stone = new LinearGradientBrush { StartPoint = new(0, 0), EndPoint = new(0, 1) };
        stone.GradientStops.Add(new GradientStop(C("4A4592"), 0));
        stone.GradientStops.Add(new GradientStop(C("26224F"), 1));
        canvas.Children.Add(new Path { Data = Geometry.Parse($"M{x - 74},{slot} L{x + 74},{slot} L{x + 90},{slot + 60} L{x - 90},{slot + 60} Z"), Fill = stone });
        Disc(canvas, x, slot + 30, 9, C("E2BE5A"), 1);
        Disc(canvas, x, slot + 30, 7, C("3A3580"), 1);
        Disc(canvas, x, slot + 30, 3.6, C("7A6AF0"), 1);
        var top = new Ellipse { Width = 152, Height = 22, Fill = new SolidColorBrush(C("5A54AC")), Stroke = new SolidColorBrush(C("E2BE5A")), StrokeThickness = 2.5 };
        Canvas.SetLeft(top, x - 76);
        Canvas.SetTop(top, slot - 11);
        canvas.Children.Add(top);
        var hole = new Ellipse { Width = 26, Height = 7, Fill = new SolidColorBrush(C("100D26")) };
        Canvas.SetLeft(hole, x - 13);
        Canvas.SetTop(hole, slot - 3.5);
        canvas.Children.Add(hole);

        // the sword, blade down into the slot: nothing of it is drawn under the stone's top
        var sword = new Canvas { Clip = new RectangleGeometry(new System.Windows.Rect(x - 40, 0, 80, slot)) };
        var t = slot - 120;   // (the pommel's top: half the blade out)
        void Part(string d, string hex) => sword.Children.Add(new Path { Data = Geometry.Parse(d), Fill = new SolidColorBrush(C(hex)) });
        Part($"M{x - 6},{t + 44} L{x + 6},{t + 44} L{x + 6},{t + 154} L{x},{t + 168} L{x - 6},{t + 154} Z", "C9D3EE");
        Part($"M{x},{t + 44} L{x + 6},{t + 44} L{x + 6},{t + 154} L{x},{t + 168} Z", "EEF2FF");
        Part($"M{x - 0.6},{t + 48} L{x + 0.6},{t + 48} L{x + 0.6},{t + 146} L{x - 0.6},{t + 146} Z", "8C98C6");
        Part($"M{x - 3.5},{t + 9} L{x + 3.5},{t + 9} L{x + 3.5},{t + 36} L{x - 3.5},{t + 36} Z", "6A5AE6");
        foreach (var k in new[] { 15.0, 22, 29 }) Part($"M{x - 3.5},{t + k} L{x + 3.5},{t + k} L{x + 3.5},{t + k + 1.6} L{x - 3.5},{t + k + 1.6} Z", "4B3CC4");
        void Dot(double cx, double cy, double r, string hex)
        {
            var e = new Ellipse { Width = 2 * r, Height = 2 * r, Fill = new SolidColorBrush(C(hex)) };
            Canvas.SetLeft(e, cx - r);
            Canvas.SetTop(e, cy - r);
            sword.Children.Add(e);
        }
        Dot(x, t + 4.5, 5.5, "E2BE5A");
        Dot(x, t + 4.5, 2.2, "6A5AE6");
        Part($"M{x - 17},{t + 36.5} L{x + 17},{t + 36.5} L{x + 17},{t + 43.5} L{x - 17},{t + 43.5} Z", "E2BE5A");
        Dot(x - 17.5, t + 40, 4, "E2BE5A");
        Dot(x + 17.5, t + 40, 4, "E2BE5A");
        Dot(x, t + 40, 5, "F6E3A6");
        Dot(x, t + 40, 3.7, "4B3CC4");
        canvas.Children.Add(sword);

        // the violet mist along the bottom
        var mist = new LinearGradientBrush { StartPoint = new(0, 0), EndPoint = new(0, 1) };
        mist.GradientStops.Add(new GradientStop(Color.FromArgb(0x00, 0x7A, 0x6A, 0xF0), 0));
        mist.GradientStops.Add(new GradientStop(Color.FromArgb(0x30, 0x7A, 0x6A, 0xF0), 1));
        var floor = new Rectangle { Width = w, Height = Math.Max(0, h - slot - 40), Fill = mist };
        Canvas.SetTop(floor, slot + 40);
        canvas.Children.Add(floor);
    }

    static void Disc(Canvas canvas, double x, double y, double r, Color colour, double opacity)
    {
        var e = new Ellipse { Width = 2 * r, Height = 2 * r, Fill = new SolidColorBrush(colour), Opacity = opacity };
        Canvas.SetLeft(e, x - r);
        Canvas.SetTop(e, y - r);
        canvas.Children.Add(e);
    }

    static void Hill(Canvas canvas, string data, Color colour) =>
        canvas.Children.Add(new Path { Data = Geometry.Parse(data), Fill = new SolidColorBrush(colour) });
}
