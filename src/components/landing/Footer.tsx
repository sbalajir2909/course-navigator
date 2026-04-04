const Footer = () => {
  return (
    <footer className="border-t py-12">
      <div className="container flex flex-col md:flex-row items-center justify-between gap-4">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded bg-primary flex items-center justify-center">
            <span className="text-primary-foreground font-serif text-sm leading-none">A</span>
          </div>
          <span className="font-serif text-lg">Assign</span>
        </div>
        <div className="flex gap-6 text-sm text-muted-foreground">
          <a href="#" className="hover:text-foreground transition-colors">Privacy</a>
          <a href="#" className="hover:text-foreground transition-colors">Terms</a>
          <a href="#" className="hover:text-foreground transition-colors">Contact</a>
        </div>
        <div className="text-sm text-muted-foreground">
          © 2026 Assign. All rights reserved.
        </div>
      </div>
    </footer>
  );
};

export default Footer;
