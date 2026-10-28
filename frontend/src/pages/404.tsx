import Head from "next/head";
import Link from "next/link";
import { Footer, Masthead } from "@/components/Masthead";

export default function NotFound() {
  return (
    <>
      <Head>
        <title>Codegen-1.5B · open circuit</title>
      </Head>
      <main className="page">
        <Masthead page="schematic" />
        <section className="sec">
          <h2 className="silk"><span className="n">404</span>Open circuit</h2>
          <div className="body">
            <p>Nothing is connected at this address.</p>
            <p><Link href="/">Back to the signal path</Link> · <Link href="/notes/">Datasheet</Link></p>
          </div>
        </section>
        <Footer />
      </main>
    </>
  );
}
